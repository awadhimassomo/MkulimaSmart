import csv
import io
import json
import shutil
import tempfile
import zipfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from PIL import Image

from assistant.models import Conversation, Message
from callcenter.models import Agronomist

from . import services
from .models import DatasetExport, LabeledImage

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix="training-tests-")


def picture(color="green", size=(40, 30), exif=False, name="leaf.jpg"):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCameraMaker"  # Make
        data[0x0112] = 1
        image.save(buffer, format="JPEG", exif=data)
    else:
        image.save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA)
class TrainingBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.counter = 0
        self.admin = User.objects.create_superuser(password="pass12345", email="admin@mkulima.test")
        self.agronomist_user = User.objects.create_user(password="pass12345", email="asha@zamseed.test")
        self.agronomist = Agronomist.objects.create(user=self.agronomist_user, full_name="Asha Mwakyusa")
        self.client = Client()
        self.client.force_login(self.agronomist_user)

    def photo(self, consent=True, phone=None, region="Mbeya", ai=None, **picture_args):
        """A farmer's photo message, plus the AI's answer to it."""
        self.counter += 1
        phone = phone or f"+2557100000{self.counter:02d}"
        conversation, _ = Conversation.objects.get_or_create(
            phone_number=phone, defaults={"farmer_name": "Niko Simiyu", "region": region, "training_consent": consent},
        )
        message = Message(conversation=conversation, role="farmer", kind="image", text="")
        message.photo.save(f"p{self.counter}.jpg", picture(**picture_args), save=False)
        message.save()
        diagnosis = ai if ai is not None else {"crop": "Papaya", "problem": "Anthracnose", "problem_type": "disease", "crop_confidence": "low", "needs_expert": True}
        Message.objects.create(conversation=conversation, role="assistant", text="reply", in_reply_to=message, payload={"diagnosis": diagnosis})
        return message

    def label(self, message, crop="Cocoa", problem="Black pod", problem_type="disease", **extra):
        return services.save_label(message, {"crop": crop, "problem": problem, "problem_type": problem_type, **extra}, self.agronomist_user, "agronomist")


class SplitTests(TrainingBase):
    def test_a_farmer_always_lands_in_the_same_set(self):
        self.assertEqual({services.split_for(7) for _ in range(5)}, {services.split_for(7)})

    def test_roughly_eighty_ten_ten(self):
        counts = {"train": 0, "val": 0, "test": 0}
        for farmer in range(2000):
            counts[services.split_for(farmer)] += 1
        self.assertAlmostEqual(counts["train"] / 2000, 0.8, delta=0.04)
        self.assertAlmostEqual(counts["val"] / 2000, 0.1, delta=0.03)
        self.assertAlmostEqual(counts["test"] / 2000, 0.1, delta=0.03)

    def test_all_of_one_farmers_photos_share_a_set(self):
        first = self.photo(phone="+255711111111")
        second = self.photo(phone="+255711111111")
        self.assertEqual(self.label(first).split, self.label(second).split)


class QueueTests(TrainingBase):
    def test_only_consented_unlabelled_photos_with_a_file_are_offered(self):
        ready = self.photo()
        self.photo(consent=False)
        self.photo(consent=None)
        done = self.photo()
        self.label(done)
        self.assertEqual(list(services.labelable()), [ready])

    def test_photos_the_ai_was_unsure_about_come_first(self):
        sure = self.photo(ai={"crop": "Maize", "problem": "Fall armyworm", "problem_type": "pest", "crop_confidence": "high", "confidence": "high"})
        unsure = self.photo()  # default guess is low confidence
        newest_sure = self.photo(ai={"crop": "Maize", "problem": "Rust", "problem_type": "disease", "crop_confidence": "high", "confidence": "high"})
        message, remaining = services.next_photo()
        self.assertEqual((message, remaining), (unsure, 3))
        message, _ = services.next_photo(skipped=[unsure.pk])
        self.assertEqual(message, newest_sure)
        self.assertNotEqual(message, sure)


class LabelTests(TrainingBase):
    def test_a_label_records_the_class_set_ai_guess_and_who(self):
        message = self.photo()
        label = self.label(message, crop="  Cocoa ", problem="Black   pod")
        self.assertEqual((label.crop, label.problem, label.crop_key, label.problem_key), ("Cocoa", "Black pod", "cocoa", "black-pod"))
        self.assertEqual((label.ai_crop, label.ai_problem), ("Papaya", "Anthracnose"))
        self.assertFalse(label.ai_agrees)
        self.assertEqual((label.label_source, label.labeled_by), ("agronomist", self.agronomist_user))
        self.assertEqual(label.split, services.split_for(message.conversation_id))
        self.assertEqual(label.class_key, "cocoa__black-pod")

    def test_the_ai_agreeing_is_recorded(self):
        message = self.photo(ai={"crop": "Cocoa", "problem": "Black pod", "problem_type": "disease"})
        self.assertTrue(self.label(message).ai_agrees)

    def test_relabelling_replaces_the_label(self):
        message = self.photo()
        self.label(message)
        self.label(message, crop="Cocoa", problem="Frosty pod rot")
        self.assertEqual(LabeledImage.objects.count(), 1)
        self.assertEqual(LabeledImage.objects.get().problem, "Frosty pod rot")

    def test_healthy_needs_no_problem_name(self):
        label = self.label(self.photo(), crop="Maize", problem="", problem_type="healthy")
        self.assertEqual((label.problem, label.problem_key), ("Healthy", "healthy"))

    def test_rejecting_marks_the_photo_unusable(self):
        label = services.save_label(self.photo(), {"reject": True, "reject_reason": "Blurry or too dark"}, self.agronomist_user, "agronomist")
        self.assertTrue(label.is_rejected)
        self.assertEqual(label.reject_reason, "Blurry or too dark")
        self.assertEqual(services.stats()["labelled"], 0)
        self.assertEqual(services.stats()["rejected"], 1)

    def test_bad_input_is_refused(self):
        message = self.photo()
        with self.assertRaises(services.LabelError):
            self.label(message, crop="")
        with self.assertRaises(services.LabelError):
            self.label(message, problem="")
        with self.assertRaises(services.LabelError):
            self.label(message, problem_type="nonsense")
        self.assertFalse(LabeledImage.objects.exists())

    def test_a_photo_without_consent_cannot_be_labelled(self):
        for consent in (False, None):
            message = self.photo(consent=consent)
            with self.assertRaises(services.LabelError):
                self.label(message)
        self.assertFalse(LabeledImage.objects.exists())


class StationTests(TrainingBase):
    def test_an_agronomist_sees_the_next_photo_with_the_ai_guess(self):
        message = self.photo()
        page = self.client.get(reverse("training_data:station"))
        self.assertContains(page, message.photo.url)
        self.assertContains(page, "The AI said")
        self.assertContains(page, "Papaya")
        self.assertContains(page, "1 photo waiting")

    def test_saving_through_the_form_moves_on(self):
        message = self.photo()
        response = self.client.post(reverse("training_data:save", args=[message.pk]), {
            "action": "save", "crop": "Cocoa", "problem": "Black pod", "problem_type": "disease",
        })
        self.assertRedirects(response, reverse("training_data:station"))
        label = LabeledImage.objects.get()
        self.assertEqual((label.crop, label.label_source), ("Cocoa", "agronomist"))
        self.assertContains(self.client.get(reverse("training_data:station")), "Nothing to label right now")

    def test_a_mistake_in_the_form_keeps_you_on_the_same_photo(self):
        message = self.photo()
        response = self.client.post(reverse("training_data:save", args=[message.pk]), {"action": "save", "crop": "", "problem": "x", "problem_type": "disease"})
        self.assertRedirects(response, f"{reverse('training_data:station')}?photo={message.pk}", fetch_redirect_response=False)
        self.assertContains(self.client.get(f"{reverse('training_data:station')}?photo={message.pk}"), "Write which crop")

    def test_rejecting_through_the_form(self):
        message = self.photo()
        self.client.post(reverse("training_data:save", args=[message.pk]), {"action": "reject", "reject_reason": "Not a crop or plant"})
        self.assertTrue(LabeledImage.objects.get().is_rejected)

    def test_skipping_shows_a_different_photo_and_comes_back_next_session(self):
        first = self.photo(ai={"crop": "A", "problem": "a", "problem_type": "pest", "crop_confidence": "high", "confidence": "high"})
        second = self.photo(ai={"crop": "B", "problem": "b", "problem_type": "pest", "crop_confidence": "high", "confidence": "high"})
        station = reverse("training_data:station")
        self.assertContains(self.client.get(station), second.photo.url)  # newest first
        self.client.post(reverse("training_data:save", args=[second.pk]), {"action": "skip"})
        self.assertContains(self.client.get(station), first.photo.url)
        self.assertFalse(LabeledImage.objects.exists())
        self.assertContains(Client_with_login(self.agronomist_user).get(station), second.photo.url)  # a new session sees it again

    def test_administrators_can_label_too(self):
        message = self.photo()
        admin = Client()
        admin.force_login(self.admin)
        self.assertEqual(admin.get(reverse("training_data:station")).status_code, 200)
        admin.post(reverse("training_data:save", args=[message.pk]), {"action": "save", "crop": "Cocoa", "problem": "Black pod", "problem_type": "disease"})
        self.assertEqual(LabeledImage.objects.get().label_source, "ops")

    def test_people_who_are_not_agronomists_are_turned_away(self):
        message = self.photo()
        outsider = Client()
        outsider.force_login(User.objects.create_user(password="pass12345", email="farmer@x.test"))
        self.assertEqual(outsider.get(reverse("training_data:station")).status_code, 403)
        self.assertEqual(outsider.post(reverse("training_data:save", args=[message.pk]), {"action": "save", "crop": "x", "problem": "y"}).status_code, 403)
        self.assertEqual(Client().get(reverse("training_data:station")).status_code, 302)
        self.assertFalse(LabeledImage.objects.exists())

    def test_a_switched_off_agronomist_cannot_label(self):
        Agronomist.objects.update(is_active=False)
        self.assertEqual(self.client.get(reverse("training_data:station")).status_code, 403)

    def test_the_console_points_agronomists_to_the_photos_waiting(self):
        self.assertNotContains(self.client.get(reverse("callcenter:console")), "Start labelling")
        self.photo()
        self.assertContains(self.client.get(reverse("callcenter:console")), "Start labelling")


def Client_with_login(user):
    client = Client()
    client.force_login(user)
    return client


class DatasetPageTests(TrainingBase):
    def test_statistics_split_counts_and_classes(self):
        for i in range(3):
            self.label(self.photo(phone=f"+25571900000{i}"))
        self.label(self.photo(), crop="Maize", problem="Fall armyworm", problem_type="pest")
        stats = services.stats()
        self.assertEqual(stats["labelled"], 4)
        self.assertEqual(sum(stats["splits"].values()), 4)
        classes = {(c["crop"], c["problem"]): c["total"] for c in stats["classes"]}
        self.assertEqual(classes, {("Cocoa", "Black pod"): 3, ("Maize", "Fall armyworm"): 1})
        self.assertEqual((stats["ai_checked"], stats["ai_agree"]), (4, 0))

    def test_a_farmer_who_withdraws_leaves_the_dataset(self):
        message = self.photo()
        self.label(message)
        self.assertEqual(services.stats()["labelled"], 1)
        Conversation.objects.update(training_consent=False)
        self.assertEqual(services.stats()["labelled"], 0)
        self.assertEqual(services.stats()["declined"], 1)

    def test_the_administrators_page(self):
        self.label(self.photo())
        admin = Client_with_login(self.admin)
        page = admin.get(reverse("training_data:dataset"))
        self.assertContains(page, "Cocoa: Black pod")
        self.assertContains(page, "Export dataset (zip)")
        self.assertContains(admin.get(reverse("ops:overview")), reverse("training_data:dataset"))  # in the navigation

    def test_only_administrators_see_it(self):
        self.assertEqual(self.client.get(reverse("training_data:dataset")).status_code, 403)
        self.assertEqual(self.client.post(reverse("training_data:export")).status_code, 403)
        self.assertEqual(Client().get(reverse("training_data:dataset")).status_code, 302)


class ExportTests(TrainingBase):
    def setUp(self):
        super().setUp()
        self.admin_client = Client_with_login(self.admin)

    def export(self):
        response = self.admin_client.post(reverse("training_data:export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        return zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))), response

    def test_the_zip_has_sets_classes_labels_and_a_readme(self):
        for i in range(5):
            self.label(self.photo(phone=f"+25572000000{i}", color=("red", "blue", "green", "yellow", "white")[i]))
        archive, response = self.export()
        names = archive.namelist()
        self.assertIn("labels.csv", names)
        self.assertIn("classes.json", names)
        self.assertIn("README.txt", names)
        images = [n for n in names if n.endswith(".jpg")]
        self.assertEqual(len(images), 5)
        self.assertTrue(all(n.split("/")[0] in ("train", "val", "test") and n.split("/")[1] == "cocoa__black-pod" for n in images))
        self.assertIn("attachment", response["Content-Disposition"])
        rows = list(csv.DictReader(io.StringIO(archive.read("labels.csv").decode())))
        self.assertEqual(len(rows), 5)
        self.assertEqual({r["crop"] for r in rows}, {"Cocoa"})
        self.assertEqual(sum(sum(v[s] for s in ("train", "val", "test")) for v in json.loads(archive.read("classes.json")).values()), 5)

    def test_it_never_contains_names_numbers_or_exif(self):
        self.label(self.photo(phone="+255733333333", exif=True))
        archive, _ = self.export()
        everything = b"".join(archive.read(n) for n in archive.namelist() if not n.endswith(".jpg")).decode()
        self.assertNotIn("+255733333333", everything)
        self.assertNotIn("255733333333", everything)
        self.assertNotIn("Niko", everything)
        jpg = next(n for n in archive.namelist() if n.endswith(".jpg"))
        cleaned = Image.open(io.BytesIO(archive.read(jpg)))
        self.assertEqual(dict(cleaned.getexif()), {})
        self.assertNotIn(b"SecretCameraMaker", archive.read(jpg))

    def test_large_photos_are_shrunk(self):
        self.label(self.photo(size=(3000, 2000)))
        archive, _ = self.export()
        jpg = next(n for n in archive.namelist() if n.endswith(".jpg"))
        self.assertEqual(max(Image.open(io.BytesIO(archive.read(jpg))).size), 1024)

    def test_only_confirmed_usable_consented_photos_are_included(self):
        good = self.label(self.photo(phone="+255740000001", color="red"))
        self.photo(phone="+255740000002", color="blue")  # never labelled
        services.save_label(self.photo(phone="+255740000003", color="green"), {"reject": True}, self.agronomist_user, "agronomist")
        withdrawn = self.photo(phone="+255740000004", color="yellow")
        self.label(withdrawn)
        Conversation.objects.filter(pk=withdrawn.conversation_id).update(training_consent=False)
        archive, _ = self.export()
        self.assertEqual([n for n in archive.namelist() if n.endswith(".jpg")], [f"{good.split}/cocoa__black-pod/{good.pk}.jpg"])

    def test_duplicates_and_missing_files_are_skipped_and_counted(self):
        self.label(self.photo(phone="+255750000001", color="red"))
        self.label(self.photo(phone="+255750000002", color="red"))  # the same picture again
        gone = self.photo(phone="+255750000003", color="blue")
        self.label(gone)
        gone.photo.delete(save=False)
        archive, _ = self.export()
        self.assertEqual(len([n for n in archive.namelist() if n.endswith(".jpg")]), 1)
        record = DatasetExport.objects.get()
        self.assertEqual((record.image_count, record.skipped, record.exported_by), (1, 2, self.admin))

    def test_each_export_is_recorded_and_listed(self):
        self.label(self.photo())
        self.export()
        self.export()
        self.assertEqual(DatasetExport.objects.count(), 2)
        self.assertContains(self.admin_client.get(reverse("training_data:dataset")), "Recent exports")

    def test_exporting_needs_a_post(self):
        self.assertEqual(self.admin_client.get(reverse("training_data:export")).status_code, 405)

    def test_an_empty_export_is_still_a_valid_zip(self):
        archive, _ = self.export()
        self.assertEqual(sorted(archive.namelist()), ["README.txt", "classes.json", "labels.csv"])

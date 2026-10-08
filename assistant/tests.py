import io
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import translation
from PIL import Image
from rest_framework.test import APIClient

from assistant import engine
from assistant.models import Conversation, Message
from gova_pp.diagnosis import DiagnosisError
from kikapu_bridge.models import PartnerToken
from website.models import Category, Product

User = get_user_model()
URL = "/api/kikapu-bridge/assistant/messages/"
PHONE = "+255711000001"


def photo(name="leaf.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def diagnosis_answer(**overrides):
    answer = {
        "crop": "Maize", "problem_type": "pest", "problem": "Fall armyworm", "confidence": "high", "urgency": "high",
        "summary": "Chewed leaves with frass in the whorl.", "advice": "- Scout every morning\n- Treat early",
        "product_search_terms": ["insecticide"], "needs_expert": False,
    }
    answer.update(overrides)
    return answer


@override_settings(SITE_BASE_URL="https://www.mkulimasmart.co.tz", KIKAPU_BRIDGE_REQUIRE_HTTPS=False)
class AssistantTestBase(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        supplier = User.objects.create_user(phone_number="0700000050", password="pass12345", is_supplier=True)
        category, _ = Category.objects.get_or_create(slug="crop-protection", defaults={"name": "Crop Protection"})
        self.spray = Product.objects.create(
            name="Cypermethrin Insecticide 1L", slug="cypermethrin-1l", category=category, description="Insecticide for armyworm",
            price=18000, discount_price=16000, stock=10, supplier=supplier,
        )
        _, token = PartnerToken.issue("assistant test")
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def send(self, **fields):
        fields.setdefault("phone_number", PHONE)
        return self.api.post(URL, fields, format="multipart")

    def send_photo(self, **fields):
        return self.send(image=photo(), **fields)


class PhotoFlowTests(AssistantTestBase):
    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer())
    def test_photo_gets_diagnosis_and_marketplace_products(self, request_diagnosis):
        response = self.send_photo(farmer_name="Juma", text="majani yameliwa", language="sw", region="Simiyu", message_id="wamid.1")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        text = body["reply"]["text"]
        self.assertIn("*Maize - Fall armyworm*", text)
        self.assertIn("Cypermethrin Insecticide 1L", text)
        self.assertIn("TZS 16,000", text)  # the discounted price is the one shown
        self.assertIn("https://www.mkulimasmart.co.tz/sw/marketplace/product/cypermethrin-1l/", text)  # Swahili site for a Swahili farmer
        self.assertIn("Hatua za kuchukua", text)  # Swahili chrome
        self.assertNotIn("**", text)  # WhatsApp bold, not markdown
        self.assertEqual([p["name"] for p in body["products"]], [self.spray.name])
        self.assertEqual(body["diagnosis"]["problem"], "Fall armyworm")

        # The caption and farmer context reach the model; the photo is sent inline as a data URL.
        args = request_diagnosis.call_args.args
        self.assertTrue(args[0].startswith("data:image/png;base64,"))
        self.assertEqual(args[1]["subject"], "majani yameliwa")
        self.assertEqual(args[1]["farmer_location"], "Simiyu")
        self.assertEqual(args[2], "sw")

        conversation = Conversation.objects.get()
        self.assertEqual((conversation.phone_number, conversation.farmer_name, conversation.region), (PHONE, "Juma", "Simiyu"))
        self.assertEqual(conversation.last_diagnosis["problem"], "Fall armyworm")
        farmer_message = conversation.messages.get(role="farmer")
        self.assertEqual(farmer_message.kind, "image")
        self.assertTrue(farmer_message.photo)  # the farmer's photo is kept for staff
        self.assertEqual(conversation.messages.get(role="assistant").in_reply_to, farmer_message)

    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer(confidence="low"))
    def test_unsure_diagnosis_sends_farmer_to_an_officer(self, _):
        body = self.send_photo(language="en").json()
        self.assertTrue(body["needs_expert"])
        self.assertIn("extension officer", body["reply"]["text"])
        self.assertTrue(Conversation.objects.get().needs_expert)

    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer(problem_type="not_agricultural", product_search_terms=[], problem=""))
    def test_non_farm_photo_asks_for_a_crop_photo_and_suggests_nothing(self, _):
        body = self.send_photo(language="en").json()
        self.assertEqual(body["products"], [])
        self.assertIn("doesn't look like a crop", body["reply"]["text"])

    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer(problem_type="healthy", problem="", product_search_terms=[]))
    def test_healthy_crop_gets_no_products(self, _):
        body = self.send_photo(language="en").json()
        self.assertEqual(body["products"], [])
        self.assertIn("Ask me anything about your crop.", body["reply"]["text"])

    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer())
    def test_image_url_is_passed_to_the_model(self, request_diagnosis):
        response = self.send(image_url="https://cdn.example.com/leaf.jpg", message_id="wamid.2")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(request_diagnosis.call_args.args[0], "https://cdn.example.com/leaf.jpg")
        self.assertEqual(Message.objects.get(role="farmer").image_url, "https://cdn.example.com/leaf.jpg")


class ConversationFlowTests(AssistantTestBase):
    @mock.patch("assistant.engine.chat_completion", return_value="**Karibu!** Tuma picha ya zao lako.")
    def test_first_greeting_is_answered_by_the_model_with_no_history(self, chat_completion):
        body = self.send(text="Habari").json()
        self.assertEqual(body["reply"]["text"], "*Karibu!* Tuma picha ya zao lako.")
        system = chat_completion.call_args.args[0][0]["content"]
        self.assertIn("this is a new conversation", system)
        self.assertEqual(chat_completion.call_args.args[0][-1], {"role": "user", "content": "Habari"})

    @mock.patch("assistant.engine.chat_completion", return_value="Namba 1 ni *Cypermethrin Insecticide 1L*, TZS 16,000.")
    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer())
    def test_followup_remembers_the_photo_diagnosis_and_products(self, _, chat_completion):
        self.send_photo(language="sw", message_id="a")
        body = self.send(text="1", message_id="b").json()
        self.assertIn("Cypermethrin", body["reply"]["text"])

        messages = chat_completion.call_args.args[0]
        system = messages[0]["content"]
        self.assertIn("Fall armyworm", system)  # latest diagnosis
        self.assertIn("Cypermethrin Insecticide 1L - TZS 16,000", system)  # numbered product list
        self.assertIn("https://www.mkulimasmart.co.tz/sw/marketplace/product/cypermethrin-1l/", system)
        roles = [m["role"] for m in messages]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        self.assertIn("[The farmer sent a photo]", messages[1]["content"])
        self.assertIn("Hatua za kuchukua", messages[2]["content"])  # what we told them last turn
        self.assertEqual(messages[3]["content"], "1")
        self.assertEqual(Conversation.objects.count(), 1)  # same chat, not a new one

    @mock.patch("assistant.engine.chat_completion", return_value="Sawa.")
    def test_history_is_limited_and_in_order(self, chat_completion):
        for i in range(8):
            self.send(text=f"ujumbe {i}", message_id=f"m{i}")
        sent = [m["content"] for m in chat_completion.call_args.args[0][1:]]
        self.assertEqual(sent[-1], "ujumbe 7")
        self.assertEqual(sent[-2], "Sawa.")
        self.assertLessEqual(len(sent), engine.HISTORY_MESSAGES + 1)

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_language_follows_request_then_is_remembered(self, chat_completion):
        self.send(text="hello", language="en", message_id="1")
        self.assertIn("use English", chat_completion.call_args.args[0][0]["content"])
        self.send(text="and then?", message_id="2")  # no language this time
        self.assertEqual(Conversation.objects.get().language, "en")
        self.assertIn("use English", chat_completion.call_args.args[0][0]["content"])

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_account_is_linked_by_phone_number(self, _):
        farmer = User.objects.create_user(phone_number="0711000001", password="pass12345", is_farmer=True)
        self.send(text="hi")
        self.assertEqual(Conversation.objects.get().farmer_user, farmer)

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    def test_different_farmers_have_separate_conversations(self, _):
        self.send(text="hi")
        self.send(text="hi", phone_number="+255712222222")
        self.assertEqual(Conversation.objects.count(), 2)


class ReliabilityTests(AssistantTestBase):
    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer())
    def test_duplicate_delivery_returns_same_reply_without_a_second_model_call(self, request_diagnosis):
        first = self.send_photo(message_id="wamid.dup").json()
        second = self.send_photo(message_id="wamid.dup").json()
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["reply"]["text"], first["reply"]["text"])
        self.assertEqual(second["message_id"], first["message_id"])
        self.assertEqual(request_diagnosis.call_count, 1)
        self.assertEqual(Message.objects.filter(role="farmer").count(), 1)
        self.assertEqual(Message.objects.filter(role="assistant").count(), 1)

    @mock.patch("assistant.engine.request_diagnosis")
    def test_failed_attempt_is_retried_to_a_single_reply(self, request_diagnosis):
        request_diagnosis.side_effect = DiagnosisError("Could not analyse the photo right now.", status=502)
        response = self.send_photo(message_id="wamid.retry", language="en")
        self.assertEqual(response.status_code, 502)
        self.assertIn("service has a problem", response.json()["reply"]["text"])  # something Kikapu can still send
        self.assertEqual(Message.objects.filter(role="assistant").count(), 0)

        request_diagnosis.side_effect = None
        request_diagnosis.return_value = diagnosis_answer()
        response = self.send_photo(message_id="wamid.retry", language="en")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["duplicate"])
        self.assertEqual(Message.objects.filter(role="farmer").count(), 1)  # not stored twice
        self.assertEqual(Message.objects.filter(role="assistant").count(), 1)

    @mock.patch("assistant.engine.request_diagnosis", return_value=diagnosis_answer())
    @override_settings(ASSISTANT_MAX_IMAGES_PER_DAY=2)
    def test_photo_limit_per_day_blocks_before_calling_openai(self, request_diagnosis):
        self.send_photo(message_id="1")
        self.send_photo(message_id="2")
        body = self.send_photo(message_id="3", language="en").json()
        self.assertTrue(body["rate_limited"])
        self.assertIn("photo limit", body["reply"]["text"])
        self.assertEqual(request_diagnosis.call_count, 2)
        self.assertEqual(Message.objects.filter(role="farmer").count(), 2)

    @mock.patch("assistant.engine.chat_completion", return_value="ok")
    @override_settings(ASSISTANT_MAX_MESSAGES_PER_HOUR=3)
    def test_message_limit_per_hour(self, chat_completion):
        for i in range(3):
            self.send(text="hi", message_id=str(i))
        body = self.send(text="hi", message_id="4", language="en").json()
        self.assertTrue(body["rate_limited"])
        self.assertEqual(chat_completion.call_count, 3)


class RequestValidationTests(AssistantTestBase):
    def test_requires_partner_token(self):
        self.assertEqual(APIClient().post(URL, {"phone_number": PHONE, "text": "hi"}).status_code, 401)

    def test_user_jwt_is_not_accepted(self):
        user = User.objects.create_user(phone_number="0700000051", password="pass12345")
        from rest_framework_simplejwt.tokens import RefreshToken
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        self.assertEqual(client.post(URL, {"phone_number": PHONE, "text": "hi"}).status_code, 401)

    def test_phone_number_required_and_normalised(self):
        self.assertEqual(self.api.post(URL, {"text": "hi"}, format="json").status_code, 400)
        with mock.patch("assistant.engine.chat_completion", return_value="ok"):
            self.api.post(URL, {"phone_number": "0711000001", "text": "hi"}, format="json")
        self.assertEqual(Conversation.objects.get().phone_number, "+255711000001")

    def test_needs_text_or_photo(self):
        response = self.api.post(URL, {"phone_number": PHONE, "language": "en"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("type a message", response.json()["reply"]["text"])
        self.assertEqual(Conversation.objects.count(), 0)

    def test_corrupt_photo_is_rejected_with_a_sendable_reply(self):
        fake = SimpleUploadedFile("leaf.png", b"not an image", content_type="image/png")
        with mock.patch("assistant.engine.request_diagnosis") as request_diagnosis:
            response = self.send(image=fake, language="en")
        self.assertEqual(response.status_code, 400)
        self.assertIn("could not read that photo", response.json()["reply"]["text"])
        request_diagnosis.assert_not_called()

    def test_json_body_with_text_works(self):
        with mock.patch("assistant.engine.chat_completion", return_value="Habari!"):
            response = self.api.post(URL, json.dumps({"phone_number": PHONE, "text": "Habari"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"]["text"], "Habari!")

    def test_missing_openai_key_is_503_with_sendable_reply(self):
        with override_settings(OPENAI_API_KEY=""):
            response = self.api.post(URL, {"phone_number": PHONE, "text": "hi", "language": "en"}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertIn("service has a problem", response.json()["reply"]["text"])


class FormattingTests(TestCase):
    def test_markdown_becomes_whatsapp_formatting(self):
        self.assertEqual(engine.to_whatsapp("## Title\n**bold** text\r\n- item"), "Title\n*bold* text\n- item")

    def test_reply_is_capped(self):
        self.assertEqual(len(engine.to_whatsapp("x" * 5000)), engine.MAX_REPLY_CHARS)

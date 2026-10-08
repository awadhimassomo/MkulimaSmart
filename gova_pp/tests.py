import io
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from gova_pp import diagnosis as dx
from website.models import Category, Product

User = get_user_model()

ENDPOINT = "/api/ai/analyze-image/"


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format="PNG")
    return buffer.getvalue()


def model_answer(**overrides):
    """What GPT-4o is asked to return, before normalisation."""
    answer = {
        "crop": "Maize", "problem_type": "pest", "problem": "Fall armyworm", "confidence": "high", "urgency": "high",
        "summary": "Chewed leaves with frass in the whorl.", "advice": "- Scout every morning\n- Treat early",
        "product_search_terms": ["insecticide", "cypermethrin"], "needs_expert": False,
    }
    answer.update(overrides)
    return answer


class MarketplaceTestBase(TestCase):
    def setUp(self):
        self.supplier = User.objects.create_user(phone_number="0700000040", password="pass12345", is_supplier=True)
        # Marketplace categories are seeded by a data migration; reuse them.
        self.protection, _ = Category.objects.get_or_create(slug="crop-protection", defaults={"name": "Crop Protection"})
        self.fertilizers, _ = Category.objects.get_or_create(slug="fertilizers", defaults={"name": "Fertilizers"})
        self.seeds, _ = Category.objects.get_or_create(slug="seeds", defaults={"name": "Seeds"})

    def product(self, name, category, slug=None, description="", stock=10, **extra):
        return Product.objects.create(
            name=name, slug=slug or name.lower().replace(" ", "-"), category=category, description=description or name,
            price=extra.pop("price", 10000), stock=stock, supplier=self.supplier, **extra,
        )


class NormalizeDiagnosisTests(TestCase):
    def test_coerces_unknown_and_malformed_values(self):
        d = dx.normalize_diagnosis({
            "problem_type": "Alien invasion", "confidence": "very", "urgency": None,
            "product_search_terms": ["Fungicide", "fungicide", "ab", "  MANCOZEB  ", 5, None] + ["x" * 100],
            "needs_expert": "yes",
        })
        self.assertEqual(d["problem_type"], "other")
        self.assertEqual(d["confidence"], "low")
        self.assertEqual(d["urgency"], "medium")
        self.assertEqual(d["product_search_terms"][:2], ["fungicide", "mancozeb"])
        self.assertNotIn("ab", d["product_search_terms"])  # too short to match anything useful
        self.assertTrue(d["needs_expert"])

    def test_low_confidence_always_means_expert(self):
        self.assertTrue(dx.normalize_diagnosis(model_answer(confidence="low", needs_expert=False))["needs_expert"])
        self.assertFalse(dx.normalize_diagnosis(model_answer(confidence="high", needs_expert=False))["needs_expert"])


class RecommendProductsTests(MarketplaceTestBase):
    def test_pest_recommends_crop_protection_with_term_match_first(self):
        generic = self.product("Farm Spray Guard", self.protection, description="General crop protection")
        exact = self.product("Cypermethrin Insecticide 1L", self.protection, description="Controls armyworm in maize")
        self.product("Urea 46%", self.fertilizers)
        self.product("Maize Seed H614", self.seeds, description="Hybrid maize seed")

        diagnosis = dx.normalize_diagnosis(model_answer())
        names = [p["name"] for p in dx.recommend_products(diagnosis)]
        self.assertEqual(names[0], exact.name)
        self.assertIn(generic.name, names)
        self.assertNotIn("Urea 46%", names)
        self.assertNotIn("Maize Seed H614", names)  # a crop-name match must not recommend seed for a pest

    def test_excludes_out_of_stock_and_inactive(self):
        self.product("Insecticide Sold Out", self.protection, stock=0)
        self.product("Insecticide Retired", self.protection, is_active=False)
        live = self.product("Insecticide Live", self.protection)
        names = [p["name"] for p in dx.recommend_products(dx.normalize_diagnosis(model_answer()))]
        self.assertEqual(names, [live.name])

    def test_nutrient_deficiency_recommends_fertilizers(self):
        npk = self.product("NPK 17-17-17", self.fertilizers)
        self.product("Cypermethrin Insecticide", self.protection)
        diagnosis = dx.normalize_diagnosis(model_answer(problem_type="nutrient_deficiency", product_search_terms=["npk"]))
        self.assertEqual([p["name"] for p in dx.recommend_products(diagnosis)], [npk.name])

    def test_healthy_or_not_agricultural_recommends_nothing(self):
        self.product("Cypermethrin Insecticide", self.protection)
        for problem_type in ("healthy", "not_agricultural"):
            diagnosis = dx.normalize_diagnosis(model_answer(problem_type=problem_type))
            self.assertEqual(dx.recommend_products(diagnosis), [])

    def test_limit_and_result_shape(self):
        for i in range(5):
            self.product(f"Insecticide {i}", self.protection, discount_price=8000)
        results = dx.recommend_products(dx.normalize_diagnosis(model_answer()), limit=3)
        self.assertEqual(len(results), 3)
        first = results[0]
        self.assertEqual(set(first), {"id", "name", "category", "price", "discount_price", "stock", "requires_quote",
                                      "image", "url", "matched_terms"})
        self.assertEqual(first["discount_price"], 8000.0)
        self.assertIn("insecticide", first["matched_terms"])


@override_settings(OPENAI_API_KEY="test-key")
class AnalyzeImageEndpointTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.farmer = User.objects.create_user(phone_number="0700000041", password="pass12345", is_farmer=True)
        self.client.force_login(self.farmer)
        self.spray = self.product("Cypermethrin Insecticide 1L", self.protection)

    def post_json(self, payload):
        return self.client.post(ENDPOINT, data=json.dumps(payload), content_type="application/json")

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.post_json({"image_url": "https://example.com/a.jpg"}).status_code, 401)

    def test_requires_an_image(self):
        self.assertEqual(self.post_json({}).status_code, 400)

    @mock.patch("gova_pp.ai_views.request_diagnosis", return_value=model_answer())
    def test_image_url_returns_diagnosis_and_products(self, request_diagnosis):
        response = self.post_json({"image_url": "https://example.com/leaf.jpg", "media_id": 7, "language": "sw"})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["media_id"], 7)
        self.assertIn("Fall armyworm", body["analysis"])  # old clients still get a readable `analysis`
        self.assertEqual(body["diagnosis"]["problem_type"], "pest")
        self.assertEqual([p["name"] for p in body["recommended_products"]], [self.spray.name])
        self.assertTrue(body["recommended_products"][0]["url"].startswith("http://testserver/"))
        # The remote URL is handed to the model unchanged, with the requested language.
        args = request_diagnosis.call_args.args
        self.assertEqual(args[0], "https://example.com/leaf.jpg")
        self.assertEqual(args[2], "sw")

    @mock.patch("gova_pp.ai_views.request_diagnosis", return_value=model_answer())
    def test_multipart_upload_is_sent_inline(self, request_diagnosis):
        upload = SimpleUploadedFile("leaf.png", png_bytes(), content_type="image/png")
        response = self.client.post(ENDPOINT, {"image": upload})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(request_diagnosis.call_args.args[0].startswith("data:image/png;base64,"))

    def test_non_image_upload_rejected_before_calling_openai(self):
        upload = SimpleUploadedFile("notes.png", b"definitely not an image", content_type="image/png")
        with mock.patch("gova_pp.ai_views.request_diagnosis") as request_diagnosis:
            response = self.client.post(ENDPOINT, {"image": upload})
        self.assertEqual(response.status_code, 400)
        request_diagnosis.assert_not_called()

    def test_media_path_cannot_escape_media_root(self):
        with mock.patch("gova_pp.ai_views.request_diagnosis") as request_diagnosis:
            response = self.post_json({"image_url": "/media/../MkulimaSmart/settings.py"})
        self.assertEqual(response.status_code, 400)
        request_diagnosis.assert_not_called()

    @mock.patch("gova_pp.ai_views.request_diagnosis", return_value=model_answer(problem_type="not_agricultural", product_search_terms=[]))
    def test_not_agricultural_photo_gets_no_products(self, _):
        body = self.post_json({"image_url": "https://example.com/selfie.jpg"}).json()
        self.assertEqual(body["recommended_products"], [])

    @mock.patch("gova_pp.ai_views.request_diagnosis", side_effect=dx.DiagnosisError("Could not analyse the photo right now.", status=502))
    def test_model_failure_is_reported_not_swallowed(self, _):
        response = self.post_json({"image_url": "https://example.com/leaf.jpg"})
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIn("Could not analyse", body["analysis"])  # still readable by clients that only show `analysis`

    @override_settings(OPENAI_API_KEY="")
    def test_missing_api_key_is_503(self):
        response = self.post_json({"image_url": "https://example.com/leaf.jpg"})
        self.assertEqual(response.status_code, 503)


@override_settings(OPENAI_API_KEY="test-key")
class RequestDiagnosisTests(TestCase):
    def fake_openai(self, content):
        client = mock.Mock()
        client.chat.completions.create.return_value = mock.Mock(choices=[mock.Mock(message=mock.Mock(content=content))])
        return mock.patch("openai.OpenAI", return_value=client), client

    def test_parses_json_and_sends_image_and_language(self):
        patcher, client = self.fake_openai(json.dumps(model_answer()))
        with patcher:
            result = dx.request_diagnosis("https://example.com/leaf.jpg", {"farmer_location": "Simiyu"}, "sw")
        self.assertEqual(result["problem"], "Fall armyworm")
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertIn("Swahili", kwargs["messages"][0]["content"])
        self.assertIn("Simiyu", kwargs["messages"][0]["content"])
        self.assertEqual(kwargs["messages"][1]["content"][1]["image_url"]["url"], "https://example.com/leaf.jpg")

    def test_unreadable_model_output_is_a_502(self):
        patcher, _ = self.fake_openai("Sorry, I can't help with that.")
        with patcher, self.assertRaises(dx.DiagnosisError) as raised:
            dx.request_diagnosis("https://example.com/leaf.jpg")
        self.assertEqual(raised.exception.status, 502)

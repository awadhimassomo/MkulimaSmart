"""
Permission to use a farmer's photos to improve crop diagnosis (and, later, to train our own model).

Nothing is used without an explicit "yes". After the first diagnosis the farmer is asked once with two buttons;
if they do not answer we ask again on a later photo (at most MAX_ASKS times, at least a day apart) and then
stop. No answer is treated as no. The words are written here, in Swahili and English, and Kikapu only shows them.
"""
from datetime import timedelta

from django.utils import timezone

MAX_ASKS = 3
ASK_AGAIN_AFTER = timedelta(days=1)

TEXT = {
    "sw": {
        "prompt": (
            "Je, tunaweza kutumia picha zako za mazao kuboresha utambuzi wa magonjwa na wadudu? "
            "Hatutaonyesha jina wala namba yako ya simu. Ukichagua Hapana, hakuna kitakachobadilika kwako."
        ),
        "yes": "Ndiyo, nakubali",
        "no": "Hapana",
        "thanks_yes": "Asante! Picha zako zitasaidia kuboresha huduma kwa wakulima wengine. Jina na namba yako havitatumika.",
        "thanks_no": "Sawa. Hatutatumia picha zako kwa mafunzo. Huduma inaendelea kama kawaida.",
    },
    "en": {
        "prompt": (
            "May we use your crop photos to improve how we recognise crop diseases and pests? "
            "We will never show your name or phone number. If you choose No, nothing changes for you."
        ),
        "yes": "Yes, I agree",
        "no": "No thanks",
        "thanks_yes": "Thank you! Your photos will help improve the service for other farmers. Your name and number will not be used.",
        "thanks_no": "Okay. We will not use your photos for training. The service carries on as normal.",
    },
}


def _text(language):
    return TEXT.get(language, TEXT["sw"])


def prompt_for(conversation, language):
    """The question to show after a diagnosis, or None when it should not be asked now. Counts the ask."""
    if conversation.training_consent is not None or conversation.consent_asked_count >= MAX_ASKS:
        return None
    now = timezone.now()
    if conversation.consent_asked_at and now - conversation.consent_asked_at < ASK_AGAIN_AFTER:
        return None
    conversation.consent_asked_count += 1
    conversation.consent_asked_at = now
    conversation.save(update_fields=["consent_asked_count", "consent_asked_at"])
    text = _text(language)
    return {"text": text["prompt"], "yes_label": text["yes"], "no_label": text["no"]}


def record(conversation, agreed):
    """Store the farmer's answer (it can be changed by answering again). Returns the thank-you text to send."""
    conversation.training_consent = bool(agreed)
    conversation.training_consent_at = timezone.now()
    conversation.save(update_fields=["training_consent", "training_consent_at"])
    text = _text(conversation.language)
    return text["thanks_yes" if agreed else "thanks_no"]

import base64
import logging
from json import JSONEncoder

logger = logging.getLogger(__name__)

class BinaryAwareJSONEncoder(JSONEncoder):
    """
    Custom JSON encoder that properly handles binary data by base64 encoding it.
    This avoids the 'utf-8' codec can't decode byte errors in DRF responses.
    """
    def default(self, obj):
        if isinstance(obj, bytes):
            # Base64 encode any binary data
            try:
                return base64.b64encode(obj).decode('ascii')
            except Exception as e:
                logger.error(f"Error encoding binary data: {e}")
                return "[BINARY DATA]"
        # Let the parent class handle everything else
        return super().default(obj)

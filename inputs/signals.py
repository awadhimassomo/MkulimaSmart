from django.dispatch import Signal

# Sent inside the same transaction as a farmer order status change, so receivers can
# write their own rows atomically (e.g. the Kikapu webhook outbox).
# Keyword arguments: order, status, note.
farmer_order_status_changed = Signal()

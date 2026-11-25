from django.db.models.signals import post_save
from django.dispatch import receiver
from modules.fees.models import Fee
from core.notifications.services import notify_parents


@receiver(post_save, sender=Fee)
def on_fee(sender, instance, created, **kwargs):
    if not created: return
    notify_parents(instance.student,
        "Fee Payment Due",
        f"{instance.term}: ₹{instance.amount} due by {instance.due_date}",
        'announcement')

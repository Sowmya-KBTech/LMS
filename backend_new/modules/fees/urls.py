# Fees module: fees, payments, Razorpay.
from rest_framework.routers import DefaultRouter
from django.urls import path, include

from .views import (
    FeeViewSet,
    generate_fees,
    fee_ledger,
    verify_payment,
    razorpay_webhook,
)
# PHASE 3: each college's own Razorpay keys
from .payment_settings_views import (
    payment_settings,
    payment_settings_test,
    payment_status,
)

router = DefaultRouter()
router.register(r'fees', FeeViewSet, basename='fee')

urlpatterns = [
    path('generate-fees/', generate_fees),
    path('fee-ledger/', fee_ledger),

    # initiate-payment is an @action on FeeViewSet, so the router registers
    # it automatically. Only these two need a manual path.
    path('payments/verify/', verify_payment),

    # No login on the webhook - Razorpay is not a user. The webhook secret
    # is what proves the request is genuine.
    path('payments/webhook/razorpay/', razorpay_webhook),

    # PHASE 3: the college admin's Payment settings screen
    path('payments/settings/', payment_settings),
    path('payments/settings/test/', payment_settings_test),
    path('payments/status/', payment_status),

    path('', include(router.urls)),
]

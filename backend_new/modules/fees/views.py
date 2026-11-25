# ===================== IMPORTS =====================
from django.db import models
from django.db.models import Sum
from django.contrib.auth import get_user_model
from decimal import Decimal, InvalidOperation
from django.conf import settings

from rest_framework import viewsets
from rest_framework.decorators import (  api_view, permission_classes, action)
from rest_framework.permissions import ( IsAuthenticated, AllowAny)
from rest_framework.response import Response

from modules.fees.models import Fee, FeePayment, PaymentTransaction
from modules.fees.payments import (
    GatewayError,
    PaymentsNotConfigured,
    create_order,
    public_key_id,
    verify_payment_signature,
    verify_webhook_signature,
)

from modules.fees.serializers import FeeSerializer
from core.permissions import is_college_admin          # PHASE 5
from rest_framework.exceptions import PermissionDenied

User = get_user_model()


# ===================== FEE =====================
class FeeViewSet(viewsets.ModelViewSet):
    serializer_class = FeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role in ('admin', 'accounts_admin'):
            return Fee.objects.all().select_related('student')
        if user.role == 'parent':
            from core.users.models import ParentProfile
            try:
                profile = ParentProfile.objects.get(user=user)
                ids = profile.children.values_list('id', flat=True)
                return Fee.objects.filter(student_id__in=ids)
            except ParentProfile.DoesNotExist:
                return Fee.objects.none()
        if user.role == 'student':
            return Fee.objects.filter(student=user)
        return Fee.objects.none()

    # PHASE 5: raising, changing or deleting a fee is the admin's job. Students and
    # parents only read their own fees and pay through pay / initiate-payment.
    def _require_admin(self):
        if not is_college_admin(self.request.user):
            raise PermissionDenied("Only the admin or accounts admin can change fees.")

    def perform_create(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        instance.delete()

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        """
        Record ONE payment toward this fee.

        Each call creates a FeePayment row rather than incrementing a running
        total. paid_amount, status and paid_date are recalculated FROM those
        rows by the post_save signal on FeePayment, so the fee's figures can
        never disagree with its payment history.

        Body: {"amount": 2000, "reference": "RCPT-1042", "remarks": ""}
        """
        fee = self.get_object()   # already scoped by get_queryset above

        # Students and parents pay their own; the accounts admin records a
        # payment made at the office counter.
        if request.user.role not in ('parent', 'student', 'admin', 'accounts_admin'):
            return Response(
                {'detail': 'You cannot record a payment.'},
                status=403,
            )

        try:
            pay_amt = Decimal(str(request.data.get('amount')))
        except (InvalidOperation, TypeError):
            return Response({'detail': 'Enter a valid amount.'}, status=400)

        if pay_amt <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)

        # Remaining is computed from the PAYMENT ROWS, not from fee.paid_amount.
        # Two people paying at once would otherwise both read the same stale
        # total and between them could overpay the fee.
        already_paid = fee.payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        remaining = fee.amount - already_paid

        if pay_amt > remaining:
            return Response(
                {'detail': f'You can pay at most {remaining:.0f}.'},
                status=400,
            )

        # paid_by is whose money it was; recorded_by is who typed it in. They
        # differ when the office records a counter payment.
        payer = fee.student if request.user.role in ('admin', 'accounts_admin') else request.user

        # How the money arrived. Anything not in the model's choices falls back
        # to cash rather than rejecting a payment the clerk has already taken.
        mode = (request.data.get('mode') or 'cash').strip()
        if mode not in dict(FeePayment.MODE_CHOICES):
            mode = 'cash'

        FeePayment.objects.create(
            fee=fee,
            amount=pay_amt,
            mode=mode,
            paid_by=payer,
            reference=(request.data.get('reference') or '').strip(),
            remarks=(request.data.get('remarks') or '').strip(),
            recorded_by=request.user,
        )


        fee.refresh_from_db()

        return Response(FeeSerializer(fee).data)

    @action(detail=True, methods=['post'], url_path='initiate-payment')
    def initiate_payment(self, request, pk=None):
        
        fee = self.get_object()   # already scoped by get_queryset

        # Staff record counter payments through `pay`. Online checkout is for
        # the person whose money it is.
        if request.user.role not in ('parent', 'student'):
            return Response(
                {'detail': 'Only a student or parent can pay online.'},
                status=403,
            )

        # Same source of truth as `pay`: sum the rows, don't read the cache.
        already_paid = fee.payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        remaining = fee.amount - already_paid

        if remaining <= 0:
            return Response({'detail': 'This fee is already fully paid.'}, status=400)

        # No amount sent means pay the whole outstanding balance.
        raw = request.data.get('amount')
        if raw in (None, ''):
            pay_amt = remaining
        else:
            try:
                pay_amt = Decimal(str(raw))
            except (InvalidOperation, TypeError):
                return Response({'detail': 'Enter a valid amount.'}, status=400)

        if pay_amt <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=400)
        if pay_amt > remaining:
            return Response(
                {'detail': f'You can pay at most {remaining:.0f}.'},
                status=400,
            )

        # PHASE 3: the order is opened in THIS college's Razorpay account.
        try:
            order = create_order(pay_amt, receipt=f"fee-{fee.id}")
            key_id = public_key_id()
        except PaymentsNotConfigured as exc:
            return Response(
                {'detail': str(exc), 'code': 'payments_not_configured'},
                status=400,
            )
        except GatewayError as exc:
            return Response({'detail': str(exc), 'code': 'gateway_error'}, status=502)

        txn = PaymentTransaction.objects.create(
            fee=fee,
            initiated_by=request.user,
            amount=pay_amt,
            gateway_order_id=order['id'],
            raw_response=order,
        )

        # key_id is public and belongs in the checkout popup. key_secret is
        # never sent to the browser.
        return Response({
            'order_id': order['id'],
            'amount_paise': order['amount'],
            'currency': order['currency'],
            'key_id': key_id,              # this college's own Key ID
            'transaction_id': txn.id,
            'fee_term': fee.term,
            'student_name': fee.student.username,
        })


    
# ===================== GENERATE FEES (BULK) =====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_fees(request):
    if request.user.role not in ('admin', 'accounts_admin'):
        return Response({'detail': 'Only admin or accounts admin can generate fees.'}, status=403)

    course_id = request.data.get('course')
    year = request.data.get('year')
    fee_type = (request.data.get('fee_type') or '').strip()
    amount = request.data.get('amount')
    due_date = request.data.get('due_date') or None

    if not course_id or not year or not fee_type or not amount or not due_date:
        return Response(
            {'detail': 'course, year, fee_type, amount and due_date are all required.'},
            status=400,
        )
    
    students = User.objects.filter(
        role='student',
        course_id=course_id,
        year=year,
    )

    created = 0
    skipped = 0
    for s in students:
        obj, was_created = Fee.objects.get_or_create(
            student=s,
            term=fee_type,
            defaults={
                'amount': amount,
                'due_date': due_date,
                'status': 'pending',
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    return Response({
        'message': f'{created} fee(s) created, {skipped} already existed.',
        'created': created,
        'skipped': skipped,
    })


# ===================== ONLINE PAYMENT: VERIFY =====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    """
    Confirm a payment the browser has just completed.

    The browser is not trusted. Anyone can POST here claiming a payment
    succeeded; only Razorpay can produce a signature that matches our key
    secret, so the signature check is what turns a claim into a record.

    A FeePayment is created with get_or_create on gateway_payment_id. The
    webhook may confirm the same payment moments later - both paths must be
    able to run and still leave exactly one payment row.
    """
    order_id = (request.data.get('razorpay_order_id') or '').strip()
    payment_id = (request.data.get('razorpay_payment_id') or '').strip()
    signature = (request.data.get('razorpay_signature') or '').strip()

    if not (order_id and payment_id and signature):
        return Response(
            {'detail': 'Payment details are incomplete.'},
            status=400,
        )

    try:
        txn = PaymentTransaction.objects.select_related('fee').get(
            gateway_order_id=order_id
        )
    except PaymentTransaction.DoesNotExist:
        return Response({'detail': 'Unknown payment.'}, status=404)

    # The person confirming must be the person who started it.
    if txn.initiated_by_id != request.user.id:
        return Response({'detail': 'This is not your payment.'}, status=403)

    if not verify_payment_signature(order_id, payment_id, signature):
        txn.status = 'failed'
        txn.failure_reason = 'Signature verification failed.'
        txn.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return Response({'detail': 'Payment could not be verified.'}, status=400)

    # Signature is good - the money is real.
    payment, created = FeePayment.objects.get_or_create(
        gateway_payment_id=payment_id,
        defaults={
            'fee': txn.fee,
            'amount': txn.amount,
            'paid_by': txn.initiated_by,
            'recorded_by': txn.initiated_by,
            'reference': payment_id,
            'remarks': 'Paid online',
        },
    )

    txn.gateway_payment_id = payment_id
    txn.gateway_signature = signature
    txn.status = 'success'
    txn.payment = payment
    txn.save(update_fields=[
        'gateway_payment_id', 'gateway_signature',
        'status', 'payment', 'updated_at',
    ])

    # paid_amount / status / paid_date were refreshed by the post_save signal
    # on FeePayment. Re-read the fee or the response shows stale figures.
    txn.fee.refresh_from_db()

    return Response({
        'detail': 'Payment successful.',
        'already_recorded': not created,
        'fee': FeeSerializer(txn.fee).data,
    })


# ===================== ONLINE PAYMENT: WEBHOOK =====================
@api_view(['POST'])
@permission_classes([AllowAny])
def razorpay_webhook(request):
    """
    Razorpay tells us directly that a payment succeeded.
    This is the source of truth, not the browser callback. A student can
    close the tab the instant they pay; the money still moved, and this is
    how we find out.
    No login here - Razorpay is not a user. The webhook secret is what
    proves the message is genuine.
    """
    signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE', '')

    # request.body is the exact bytes Razorpay sent. Re-encoding the parsed
    # JSON would change whitespace and key order, and the hash would never
    # match - the single most common reason webhooks silently fail.
    if not verify_webhook_signature(request.body, signature):
        return Response({'detail': 'Invalid signature.'}, status=400)

    payload = request.data
    event = payload.get('event', '')

    # Only a captured payment means money has actually moved.
    if event != 'payment.captured':
        return Response({'detail': f'Ignored event {event}.'}, status=200)

    entity = (
        payload.get('payload', {})
        .get('payment', {})
        .get('entity', {})
    )
    order_id = entity.get('order_id')
    payment_id = entity.get('id')

    if not (order_id and payment_id):
        return Response({'detail': 'Malformed payload.'}, status=400)

    try:
        txn = PaymentTransaction.objects.select_related('fee').get(
            gateway_order_id=order_id
        )
    except PaymentTransaction.DoesNotExist:
        # 200, not 404 - a 404 makes Razorpay retry for hours over an order
        # that will never exist here.
        return Response({'detail': 'Unknown order.'}, status=200)

    # get_or_create on the unique gateway_payment_id. The browser callback
    # may already have recorded this payment seconds ago, and Razorpay
    # delivers webhooks at least once, not exactly once. Either path can run
    # first, twice, or both - the fee still shows one payment.
    payment, created = FeePayment.objects.get_or_create(
        gateway_payment_id=payment_id,
        defaults={
            'fee': txn.fee,
            'amount': txn.amount,
            'paid_by': txn.initiated_by,
            'recorded_by': txn.initiated_by,
            'reference': payment_id,
            'remarks': 'Paid online',
        },
    )

    txn.gateway_payment_id = payment_id
    txn.status = 'success'
    txn.payment = payment
    txn.raw_response = payload
    txn.save(update_fields=[
        'gateway_payment_id', 'status', 'payment',
        'raw_response', 'updated_at',
    ])

    return Response({'detail': 'ok', 'created': created}, status=200)


# ===================== FEE LEDGER (COUNTER VIEW) =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fee_ledger(request):
    """
    One student's complete fee position, for the collection counter.

    The fee list is organised by fee row, so a student with five heads appears
    five times scattered across five status groups. At a counter you work the
    other way round: one student in front of you, everything they owe.

    ?q=  matches roll number or username (a counter clerk has the roll number
         on a slip, not a database id)
    ?student=  exact id, once one has been picked
    """
    if request.user.role not in ('admin', 'accounts_admin'):
        return Response({'detail': 'Only admin or accounts admin.'}, status=403)

    student_id = request.query_params.get('student')
    q = (request.query_params.get('q') or '').strip()

    if not student_id and not q:
        return Response({'detail': 'Send q= to search or student= for one student.'},
                        status=400)

    # ---------- search mode: return matches, not a ledger ----------
    if not student_id:
        matches = User.objects.filter(role='student').filter(
            models.Q(roll_number__icontains=q) | models.Q(username__icontains=q)
        ).select_related('course')[:20]

        return Response({
            'mode': 'search',
            'results': [{
                'id': s.id,
                'username': s.username,
                'roll_number': s.roll_number,
                'course_name': s.course.name if s.course_id else '',
                'year': s.year,
                'semester': s.semester,
                # outstanding is what a clerk scans the list for
                'outstanding': float(
                    sum(f.amount - f.paid_amount
                        for f in Fee.objects.filter(student=s).exclude(status='paid'))
                ),
            } for s in matches],
        })

    # ---------- ledger mode ----------
    student = User.objects.filter(id=student_id, role='student').select_related(
        'course', 'department'
    ).first()
    if not student:
        return Response({'detail': 'Student not found.'}, status=404)

    fees = Fee.objects.filter(student=student).prefetch_related(
        'payments__recorded_by'
    ).order_by('due_date', 'term')

    billed = sum(f.amount for f in fees)
    collected = sum(f.paid_amount for f in fees)

    return Response({
        'mode': 'ledger',
        'student': {
            'id': student.id,
            'username': student.username,
            'roll_number': student.roll_number,
            'course_name': student.course.name if student.course_id else '',
            'department': student.department.name if student.department_id else '',
            'year': student.year,
            'semester': student.semester,
            'batch_year': student.batch_year,
        },
        'summary': {
            'billed': float(billed),
            'collected': float(collected),
            'outstanding': float(billed - collected),
            'heads': fees.count(),
            'unpaid_heads': fees.exclude(status='paid').count(),
        },
        'fees': FeeSerializer(fees, many=True).data,
    })

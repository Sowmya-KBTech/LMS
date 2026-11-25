from rest_framework import serializers
from modules.fees.models import Fee


# ===================== FEE =====================
class FeeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source='student.username', read_only=True)
    department = serializers.SerializerMethodField()
    pending_amount = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()

    def get_department(self, obj):
        dept = getattr(obj.student, 'department', None)
        return dept.name if dept else None

    def get_pending_amount(self, obj):
        return float(obj.amount) - float(obj.paid_amount)

    def get_payments(self, obj):
        """
        The payment history behind this fee. The screen used to show only the
        running total, so a clerk could not tell one ₹10,000 payment from four
        of ₹2,500, or reprint a receipt.
        """
        return [
            {
                'id': p.id,
                'amount': float(p.amount),
                'mode': p.mode,
                'mode_label': p.get_mode_display(),
                'receipt_no': p.receipt_no,
                'reference': p.reference,
                'remarks': p.remarks,
                'paid_on': p.paid_on,
                'recorded_by': p.recorded_by.username if p.recorded_by_id else '',
            }
            for p in obj.payments.all()
        ]

    class Meta:
        model = Fee
        fields = ['id', 'student', 'student_name', 'department', 'term',
                  'amount', 'paid_amount', 'pending_amount',
                  'due_date', 'paid_date', 'status', 'created_at',
                  'payments']
        read_only_fields = ['created_at']

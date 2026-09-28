
class TransactionSummaryAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        today = datetime.date.today()
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        if start_str and end_str:
            from django.utils.dateparse import parse_date
            start_date = parse_date(start_str) or today
            end_date = parse_date(end_str) or today
        else:
            start_date = today
            end_date = today

        start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

        # Total Patients (based on appointments)
        from patients.models import Appointment, Payment, Billing
        patient_count = Appointment.objects.filter(date__range=(start_date, end_date)).values('patient').distinct().count()

        # Payments Breakdown
        bills = Billing.objects.filter(is_invoice=True, created_at__range=(start_dt, end_dt))
        legacy_payments = Payment.objects.filter(patient__isnull=False, created_at__range=(start_dt, end_dt)).exclude(visit__billings__isnull=False)

        cash_total = 0.0
        upi_total = 0.0
        card_total = 0.0
        other_total = 0.0
        total_revenue = 0.0

        for b in bills:
            amt = float(b.paid_amount) if b.paid_amount is not None else 0.0
            pm = (b.payment_method or '').lower()
            if pm == 'cash': cash_total += amt
            elif pm == 'upi': upi_total += amt
            elif pm == 'card': card_total += amt
            else: other_total += amt
            total_revenue += amt

        for p in legacy_payments:
            amt = float(p.paid_amount) if p.paid_amount is not None else 0.0
            pm = (p.payment_method or '').lower()
            if pm == 'cash': cash_total += amt
            elif pm == 'upi': upi_total += amt
            elif pm == 'card': card_total += amt
            else: other_total += amt
            total_revenue += amt

        # Expenses
        expenses = Expense.objects.filter(date__range=(start_date, end_date))
        total_expenses = sum(float(e.amount) for e in expenses)

        # Net Income
        net_income = total_revenue - total_expenses

        return Response({
            'patients': patient_count,
            'payments': {
                'cash': cash_total,
                'upi': upi_total,
                'card': card_total,
                'other': other_total,
                'total': total_revenue
            },
            'expenses': {
                'total': total_expenses
            },
            'total_revenue': total_revenue,
            'net_income': net_income
        })

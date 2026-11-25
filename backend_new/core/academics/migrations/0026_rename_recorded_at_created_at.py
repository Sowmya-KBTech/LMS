from django.db import migrations


class Migration(migrations.Migration):
    """
    The FeePayment table was created with a column called recorded_at, but
    models.py was later changed to created_at without a migration. Django's
    state and the real schema have disagreed ever since, so every write to
    FeePayment failed.

    RunSQL because Django's own migration state already believes the column
    is called created_at - a RenameField would try to rename a column it
    thinks already has the new name. state_operations is empty for the same
    reason: only the database needs correcting, not Django's picture of it.

    CONDITIONAL because this repairs a drift that exists on ONE database.
    A fresh database never has recorded_at - migration 0023 creates the
    column as created_at - so an unconditional rename made the whole chain
    unrunnable from scratch. That broke every deployment and every test run,
    since the test runner builds a new database each time.
    """

    dependencies = [
        ("courses", "0025_feepayment_gateway_payment_id_paymenttransaction"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()   -- SAAS: this college's schema only
                      AND table_name = 'courses_feepayment'
                      AND column_name = 'recorded_at'
                ) THEN
                    ALTER TABLE courses_feepayment
                        RENAME COLUMN recorded_at TO created_at;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
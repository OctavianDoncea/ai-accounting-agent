import logging
from app.database import SessionLocal
from app.models.chart_of_accounts import ChartOfAccount
from app.seed.chart_of_accounts_seed import CHART_OF_ACCOUNTS_SEED

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('seed')

def seed_chart_of_accounts() -> None:
    db = SessionLocal()
    try:
        existing_codes = {code for (code,) in db.query(ChartOfAccount.account_code).all()}
        to_insert = []
        for row in CHART_OF_ACCOUNTS_SEED:
            if row['code'] in existing_codes:
                continue
            to_insert.append(
                ChartOfAccount(
                    account_code=row['code'],
                    account_name=row['name'],
                    account_type=row['type'],
                    normal_balance=row['balance'],
                    description=row.get('description'),
                    is_active=True,
                )
            )

        if to_insert:
            db.add_all(to_insert)
            db.commit()
            log.info(f'Seeded {len(to_insert)} new chart-of-accounts rows')
        else:
            log.info('Chart of accounts already seeded - no changes')
    except Exception:
        db.rollback()
        log.exception('Failed to seed chart of accounts')
        raise
    finally:
        db.close()

if __name__ == '__main__':
    seed_chart_of_accounts()
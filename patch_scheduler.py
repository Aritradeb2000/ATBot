with open(r'backend\data\scheduler.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = """# Global scheduler instance
job_defaults = {
    'misfire_grace_time': 60,
    'coalesce': True,
    'max_instances': 3
}
scheduler = AsyncIOScheduler(timezone=IST, job_defaults=job_defaults)"""

code = code.replace("scheduler = AsyncIOScheduler(timezone=IST)", replacement)

with open(r'backend\data\scheduler.py', 'w', encoding='utf-8') as f:
    f.write(code)

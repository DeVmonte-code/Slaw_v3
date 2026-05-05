import re

with open('tests/test_phase3_integration.py', 'r') as f:
    content = f.read()

# add catalog fixture or load it directly
content = content.replace("        from swiss_legal_api.engine.scan import run_benefit_scan\n", 
"""        from swiss_legal_api.engine.scan import run_benefit_scan
        from swiss_legal_api.engine.trigger import load_catalog
        catalog = load_catalog()
""")
content = content.replace("asyncio.run(run_benefit_scan(MAY5_TEST_PROFILE))", "asyncio.run(run_benefit_scan(MAY5_TEST_PROFILE, catalog))")

with open('tests/test_phase3_integration.py', 'w') as f:
    f.write(content)

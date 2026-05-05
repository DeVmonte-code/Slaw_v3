import re
with open('tests/test_phase3_integration.py') as f:
    text = f.read()

# Just revert it
text = re.sub(r'assert len\(found_sentinels\).*?\)', '''    assert len(found_sentinels) >= 3, f"Expected 3 sentinels."''', text, flags=re.DOTALL)

with open('tests/test_phase3_integration.py', 'w') as f:
    f.write(text)

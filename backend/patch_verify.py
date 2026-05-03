import re

with open("src/swiss_legal_api/engine/verify.py", "r") as f:
    code = f.read()

# Replace:
# f"SR {cit.sr_number} Art. {cit.article} in canton "
s1 = 'f"SR {cit.sr_number} Art. {cit.article} in canton "'
r1 = 'f"{\'Cantonal Law\' if cit.canton else \'SR\'} {cit.sr_number} Art. {cit.article} in canton "'

code = code.replace(s1, r1)

# Replace:
# Claim: This user is entitled to this under SR {cit.sr_number} Art. {cit.article}.
s2 = 'Claim: This user is entitled to this under SR {cit.sr_number} Art. {cit.article}.'
r2 = 'Claim: This user is entitled to this under {"Cantonal Law (" + cit.canton + ")" if getattr(cit, "canton", None) else "SR"} {cit.sr_number} Art. {cit.article}.'

code = code.replace(s2, r2)
with open("src/swiss_legal_api/engine/verify.py", "w") as f:
    f.write(code)
    

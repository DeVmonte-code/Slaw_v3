
with open("src/swiss_legal_api/engine/verify.py", "r") as f:
    lines = f.readlines()

out = []
for line in lines:
    if "f\"{'Cantonal Law' if cit.canton else 'SR'} {cit.sr_number} Art. {cit.article} in canton \"" in line:
        out.append('                f"{`Cantonal Law` if cit.canton else `SR`} {cit.sr_number} "\n'.replace("`", "'"))
        out.append('                f"Art. {cit.article} in canton "\n')
    elif "Claim: This user is entitled to this under {\"Cantonal Law (\" + cit.canton + \")\" if getattr(cit, \"canton\", None) else \"SR\"} {cit.sr_number} Art. {cit.article}." in line:
        out.append('    law_txt = f"Cantonal Law ({cit.canton})" if getattr(cit, "canton", None) else "SR"\n')
        out.append('    user_content = f"""Entitlement: {entitlement.title.en}\n')
        out.append('Claim: This user is entitled to this under {law_txt} {cit.sr_number} Art. {cit.article}.\n')
    elif '    user_content = f"""Entitlement: {entitlement.title.en}\n' in line:
        pass
    else:
        out.append(line)

with open("src/swiss_legal_api/engine/verify.py", "w") as f:
    f.writelines(out)

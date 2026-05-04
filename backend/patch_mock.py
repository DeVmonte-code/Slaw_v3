def patch_file():
    with open("tests/test_admin_audits.py", "r") as f:
        content = f.read()
    content = content.replace('latency_ms=100', '\n                    latency_ms=100\n')
    content = content.replace('lambda *a, **kw: [rep1, rep2]', 'lambda *a, **kw: [\n        rep1, rep2\n    ]')
    with open("tests/test_admin_audits.py", "w") as f:
        f.write(content)

patch_file()

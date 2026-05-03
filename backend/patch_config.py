with open("src/swiss_legal_api/config.py", "r") as f:
    text = f.read()

if "fedlex_refresh_enabled: bool = False" not in text:
    text = text.replace("    sweep_enabled: bool = False", "    sweep_enabled: bool = False\n    # When True, the nightly schedule will fetch new data from Fedlex\n    # and then promote it. Disabled by default.\n    fedlex_refresh_enabled: bool = False")
    with open("src/swiss_legal_api/config.py", "w") as f:
        f.write(text)

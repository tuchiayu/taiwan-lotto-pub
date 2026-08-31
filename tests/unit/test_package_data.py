from importlib.resources import files


def test_web_templates_and_static_assets_are_packaged() -> None:
    web_files = files("taiwan_lotto.web")

    assert web_files.joinpath("templates/index.html").is_file()
    assert web_files.joinpath("templates/stats.html").is_file()
    assert web_files.joinpath("static/app.css").is_file()
    assert web_files.joinpath("static/stats.js").is_file()
    assert web_files.joinpath("static/browser.js").is_file()

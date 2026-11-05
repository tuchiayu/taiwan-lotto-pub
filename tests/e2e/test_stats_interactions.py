"""Exercise the rendered statistics UI through Chromium input events."""

import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Locator, Page, expect

COUNT_DESC = [1, 2, 3, 4, 8, 9, 12, 5, 6, 10, 13, 14]
UNSEEN_MAIN = [7, 11, *range(15, 50)]


def assert_numbers(panel: Locator, numbers: list[int]) -> None:
    expect(panel.locator("tbody th")).to_have_text([f"{n:02d}" for n in numbers])


def assert_sort(page: Page, table: str, field: str, order: str) -> None:
    panel = page.locator(f"#{table}-panel")
    header = panel.locator("thead th").filter(
        has=page.locator(f'[data-sort-field="{field}"]')
    )
    expect(header).to_have_attribute(
        "aria-sort", "ascending" if order == "asc" else "descending"
    )
    expect(panel.locator("thead th[aria-sort]")).to_have_count(1)
    query = parse_qs(urlsplit(page.url).query)
    assert query[f"{table}_sort"] == [field]
    assert query[f"{table}_order"] == [order]
    assert query["table"] == [table]


def assert_tab(page: Page, active: str, *, focused: bool = False) -> None:
    other = "special" if active == "main" else "main"
    expect(page.locator(f"#{active}-panel")).to_be_visible()
    expect(page.locator(f"#{other}-panel")).to_be_hidden()
    expect(page.locator(f"#{active}-tab")).to_have_attribute("aria-selected", "true")
    expect(page.locator(f"#{active}-tab")).to_have_attribute("tabindex", "0")
    expect(page.locator(f"#{other}-tab")).to_have_attribute("aria-selected", "false")
    expect(page.locator(f"#{other}-tab")).to_have_attribute("tabindex", "-1")
    expect(page.locator("[data-active-table-input]")).to_have_value(active)
    expect(page).to_have_url(re.compile(rf"[?&]table={active}(?:&|$)"))
    if focused:
        expect(page.locator(f"#{active}-tab")).to_be_focused()


@pytest.mark.parametrize("field", ["count", "rate", "expected_difference"])
def test_numeric_sort_keeps_ties_in_number_order(stats_page: Page, field: str) -> None:
    panel = stats_page.locator("#main-panel")
    link = panel.locator(f'a[data-sort-field="{field}"]')
    if field == "count":
        # Count is initially descending; other numeric columns start with DESC.
        link.click()
    else:
        link.click()
        assert_numbers(panel, COUNT_DESC + UNSEEN_MAIN)
        assert_sort(stats_page, "main", field, "desc")
        link.click()
    assert_numbers(panel, UNSEEN_MAIN + [5, 6, 10, 13, 14, 8, 9, 12, 2, 3, 4, 1])
    assert_sort(stats_page, "main", field, "asc")
    link.click()
    assert_numbers(panel, COUNT_DESC + UNSEEN_MAIN)
    assert_sort(stats_page, "main", field, "desc")


def test_number_sort_and_special_sort_are_independent(stats_page: Page) -> None:
    main = stats_page.locator("#main-panel")
    main.locator('a[data-sort-field="number"]').click()
    assert_numbers(main, list(range(1, 50)))
    assert_sort(stats_page, "main", "number", "asc")
    main.locator('a[data-sort-field="number"]').click()
    assert_numbers(main, list(range(49, 0, -1)))
    assert_sort(stats_page, "main", "number", "desc")

    stats_page.get_by_role("tab", name="特別號", exact=True).click()
    assert_tab(stats_page, "special")
    special = stats_page.locator("#special-panel")
    special.locator('a[data-sort-field="count"]').click()
    assert_numbers(
        special, [n for n in range(1, 50) if n not in (7, 11, 15)] + [11, 15, 7]
    )
    assert_sort(stats_page, "special", "count", "asc")
    special.locator('a[data-sort-field="count"]').click()
    assert_numbers(
        special, [7, 11, 15] + [n for n in range(1, 50) if n not in (7, 11, 15)]
    )
    assert_sort(stats_page, "special", "count", "desc")

    stats_page.get_by_role("tab", name="獎號", exact=True).click()
    assert_tab(stats_page, "main")
    assert_numbers(main, list(range(49, 0, -1)))
    assert_sort(stats_page, "main", "number", "desc")


def test_date_sort_keeps_unseen_numbers_last_in_both_directions(
    stats_page: Page,
) -> None:
    panel = stats_page.locator("#main-panel")
    link = panel.locator('a[data-sort-field="last_seen_date"]')
    link.click()
    assert_numbers(panel, [1, 3, 4, 9, 12, 14, 2, 8, 13, 10, 5, 6] + UNSEEN_MAIN)
    assert_sort(stats_page, "main", "last_seen_date", "desc")
    link.click()
    assert_numbers(panel, [5, 6, 10, 2, 8, 13, 1, 3, 4, 9, 12, 14] + UNSEEN_MAIN)
    assert_sort(stats_page, "main", "last_seen_date", "asc")


def test_keyboard_tabs_update_focus_selection_and_url(stats_page: Page) -> None:
    stats_page.get_by_role("tab", name="獎號", exact=True).focus()
    for key, table in [
        ("ArrowRight", "special"),
        ("ArrowRight", "main"),
        ("ArrowLeft", "special"),
        ("Home", "main"),
        ("End", "special"),
    ]:
        stats_page.keyboard.press(key)
        assert_tab(stats_page, table, focused=True)


def test_browser_back_and_forward_restore_selected_tab(stats_page: Page) -> None:
    assert_tab(stats_page, "main")
    stats_page.get_by_role("tab", name="特別號", exact=True).click()
    assert_tab(stats_page, "special")
    stats_page.get_by_role("tab", name="獎號", exact=True).click()
    assert_tab(stats_page, "main")

    stats_page.go_back()
    assert_tab(stats_page, "special")
    stats_page.go_back()
    assert_tab(stats_page, "main")
    stats_page.go_forward()
    assert_tab(stats_page, "special")
    stats_page.go_forward()
    assert_tab(stats_page, "main")


def assert_history_state(
    page: Page,
    url: str,
    active: str,
    main: tuple[str, str, list[int]],
    special: tuple[str, str, list[int]],
) -> None:
    expect(page).to_have_url(url)
    assert_tab(page, active)
    query = parse_qs(urlsplit(url).query)
    labels = {"number": "號碼", "count": "開出次數", "last_seen_date": "最近開出"}
    for table, (field, order, numbers) in [("main", main), ("special", special)]:
        panel = page.locator(f"#{table}-panel")
        assert_numbers(panel, numbers)
        assert query.get(f"{table}_sort", ["count"]) == [field]
        assert query.get(f"{table}_order", ["desc"]) == [order]
        expect(panel.locator("thead th[aria-sort]")).to_have_count(1)
        expect(panel.locator("thead th[aria-sort]")).to_have_attribute(
            "aria-sort", "ascending" if order == "asc" else "descending"
        )
        expect(panel.locator("thead th[aria-sort] a")).to_have_attribute(
            "data-sort-field", field
        )
        if table == active:
            direction = "由小到大" if order == "asc" else "由大到小"
            expect(page.locator("[data-sort-status]")).to_have_text(
                f"{labels[field]}，{direction}"
            )
        for link in panel.locator("[data-sort-link]").all():
            link_field = link.get_attribute("data-sort-field")
            next_order = (
                ("desc" if order == "asc" else "asc")
                if link_field == field
                else ("asc" if link_field == "number" else "desc")
            )
            expected_query = {
                **query,
                "table": [table],
                f"{table}_sort": [link_field],
                f"{table}_order": [next_order],
            }
            assert (
                parse_qs(urlsplit(link.get_attribute("href")).query) == expected_query
            )


@pytest.mark.parametrize("field", ["number", "last_seen_date", "count"])
def test_history_restores_both_table_sorts(stats_page: Page, field: str) -> None:
    main = stats_page.locator("#main-panel")
    special = stats_page.locator("#special-panel")
    main_link = main.locator(f'a[data-sort-field="{field}"]')
    special_link = special.locator('a[data-sort-field="last_seen_date"]')
    initial_main, changed_main = {
        "number": (
            ("number", "asc", list(range(1, 50))),
            ("number", "desc", list(range(49, 0, -1))),
        ),
        "last_seen_date": (
            (
                "last_seen_date",
                "desc",
                [1, 3, 4, 9, 12, 14, 2, 8, 13, 10, 5, 6] + UNSEEN_MAIN,
            ),
            (
                "last_seen_date",
                "asc",
                [5, 6, 10, 2, 8, 13, 1, 3, 4, 9, 12, 14] + UNSEEN_MAIN,
            ),
        ),
        "count": (
            ("count", "desc", COUNT_DESC + UNSEEN_MAIN),
            ("count", "asc", UNSEEN_MAIN + [5, 6, 10, 13, 14, 8, 9, 12, 2, 3, 4, 1]),
        ),
    }[field]
    unseen_special = [number for number in range(1, 50) if number not in (7, 11, 15)]
    initial_special = ("count", "desc", [7, 11, 15] + unseen_special)
    special_asc = ("last_seen_date", "asc", [11, 7, 15] + unseen_special)
    special_desc = ("last_seen_date", "desc", [15, 7, 11] + unseen_special)
    if field != "count":
        main_link.click()
    first_url = stats_page.url
    initial_length = stats_page.evaluate("history.length")
    stats_page.evaluate("""() => {
        window.__historyWrites = [];
        for (const name of ['pushState', 'replaceState']) {
            const original = history[name].bind(history);
            history[name] = (...args) => {
                window.__historyWrites.push(name);
                return original(...args);
            };
        }
    }""")
    stats_page.locator("#special-tab").click()
    special_link.click()
    special_link.click()
    second_url = stats_page.url
    stats_page.locator("#main-tab").click()
    main_link.click()
    third_url = stats_page.url
    stats_page.locator("#special-tab").click()
    special_link.click()
    fourth_url = stats_page.url
    expected_writes = [
        "pushState",
        "replaceState",
        "replaceState",
        "pushState",
        "replaceState",
        "pushState",
        "replaceState",
    ]
    assert stats_page.evaluate("window.__historyWrites") == expected_writes
    assert stats_page.evaluate("history.length") == initial_length + 3

    for navigate, url, active, main_state, special_state in [
        (stats_page.go_back, third_url, "main", changed_main, special_asc),
        (stats_page.go_back, second_url, "special", initial_main, special_asc),
        (stats_page.go_back, first_url, "main", initial_main, initial_special),
        (stats_page.go_forward, second_url, "special", initial_main, special_asc),
        (stats_page.go_forward, third_url, "main", changed_main, special_asc),
        (stats_page.go_forward, fourth_url, "special", changed_main, special_desc),
    ]:
        navigate()
        assert_history_state(stats_page, url, active, main_state, special_state)
        assert stats_page.evaluate("window.__historyWrites") == expected_writes
        assert stats_page.evaluate("history.length") == initial_length + 3

    # A new click must toggle the restored direction and preserve the other table.
    special_link.click()
    assert_history_state(
        stats_page, stats_page.url, "special", changed_main, special_asc
    )


def test_history_restores_fallback_on_invalid_or_empty_sort_parameters(
    stats_page: Page,
) -> None:
    unseen_special = [number for number in range(1, 50) if number not in (7, 11, 15)]
    default_main = COUNT_DESC + UNSEEN_MAIN
    default_special = [7, 11, 15] + unseen_special

    stats_page.locator('#main-panel a[data-sort-field="number"]').click()
    stats_page.locator("#special-tab").click()
    stats_page.locator('#special-panel a[data-sort-field="number"]').click()

    stats_page.evaluate(
        """() => {
            history.pushState(
                { table: 'main' },
                '',
                '/stats?game=lotto649&table=main&main_sort=unknown_field&main_order=invalid_order&special_sort='
            );
            window.dispatchEvent(new PopStateEvent('popstate'));
        }"""
    )
    assert_tab(stats_page, "main")
    assert_numbers(stats_page.locator("#main-panel"), default_main)
    assert_numbers(stats_page.locator("#special-panel"), default_special)
    expect(stats_page.locator("#main-panel thead th[aria-sort]")).to_have_attribute(
        "aria-sort", "descending"
    )
    expect(stats_page.locator("#main-panel thead th[aria-sort] a")).to_have_attribute(
        "data-sort-field", "count"
    )
    expect(stats_page.locator("#special-panel thead th[aria-sort]")).to_have_attribute(
        "aria-sort", "descending"
    )
    expect(
        stats_page.locator("#special-panel thead th[aria-sort] a")
    ).to_have_attribute("data-sort-field", "count")
    expect(stats_page.locator("[data-sort-status]")).to_have_text("開出次數，由大到小")

import unittest
from unittest.mock import Mock, patch

from flow.linkedin_auth import (
    PASSWORD_LOCATORS,
    SIGN_IN_LOCATORS,
    SUBMIT_LOCATORS,
    USERNAME_LOCATORS,
    get_build_locators,
    first_visible_locator
)

class LocatorDefinitionTests(unittest.TestCase):
    def test_supported_strategies(self):
        cases = [
            ({"strategy": "role", "role": "button", "name": "Continue"},
             "get_by_role", ("button",), {"name": "Continue", "exact": True}),
            ({"strategy": "label", "name": "Password"},
             "get_by_label", ("Password",), {"exact": True}),
            ({"strategy": "placeholder", "name": "Search", "exact": False},
             "get_by_placeholder", ("Search",), {"exact": False}),
            ({"strategy": "css", "selector": "#legacy"},
             "locator", ("#legacy",), {})
        ]
        for definition, method, args, kwargs in cases:
            with self.subTest(strategy=definition["strategy"]):
                page = Mock()
                result = get_build_locators(page, definition)
                factory = getattr(page, method)
                factory.assert_called_once_with(*args, **kwargs)
                self.assertIs(result, factory.return_value)

    def test_optional_scope(self):
        page = Mock()
        definition = {
            "strategy": "role", "role": "button", "name": "Sign in",
            "scope": {"strategy": "role", "role": "dialog", "name": "Login"}
        }
        get_build_locators(page, definition)
        page.get_by_role.assert_called_once_with("dialog", name="Login", exact=True)
        page.get_by_role.return_value.get_by_role.assert_called_once_with(
            "button", name="Sign in", exact=True
        )

    def test_invalid_strategy_fails_immediately(self):
        with self.assertRaisesRegex(ValueError, "Unsupported locator strategy"):
            first_visible_locator(Mock(), [{"strategy": "typo"}])

    @patch("flow.linkedin_auth.time.monotonic", side_effect=[0, 0, 0.1])
    def test_delayed_element_is_retried(self, clock):
        page = Mock()
        locator = page.get_by_role.return_value
        locator.count.side_effect = [0, 1]
        locator.is_visible.return_value = True
        locator.is_enabled.return_value = True
        result, description = first_visible_locator(page, SUBMIT_LOCATORS)
        self.assertIs(result, locator)
        self.assertIn("Sign in", description)
        page.wait_for_timeout.assert_called_once_with(250)
        locator.nth.assert_not_called()

    @patch("flow.linkedin_auth.time.monotonic", side_effect=[0, 0, 0.1])
    def test_disabled_element_is_retried(self, clock):
        page = Mock()
        locator = page.get_by_role.return_value
        locator.count.return_value = 1
        locator.is_visible.return_value = True
        locator.is_enabled.side_effect = [False, True]
        result, _ = first_visible_locator(page, SUBMIT_LOCATORS)
        self.assertIs(result, locator)
        page.wait_for_timeout.assert_called_once_with(250)

    @patch("flow.linkedin_auth.time.monotonic", side_effect=[0, 0, 4])
    def test_missing_element_returns_none_on_timeout(self, clock):
        page = Mock()
        page.get_by_role.return_value.count.return_value = 0
        self.assertEqual(first_visible_locator(page, SUBMIT_LOCATORS), (None, None))

    def test_duplicate_matches_fail_without_falling_back(self):
        page = Mock()
        page.get_by_role.return_value.count.return_value = 2
        definitions = SUBMIT_LOCATORS + [{"strategy": "label", "name": "Fallback"}]
        with self.assertRaisesRegex(RuntimeError, "Ambiguous locator.*2 elements"):
            first_visible_locator(page, definitions)
        page.get_by_role.return_value.nth.assert_not_called()
        page.get_by_label.return_value.count.assert_not_called()


class LocatorBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(channel="chrome", headless=True)
        except Exception as e:
            cls.playwright.stop()
            raise unittest.SkipTest(f"Chrome unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    def test_login_fields_and_distinct_sign_in_roles(self):
        self.page.set_content('''
            <a href="#login">Sign in</a>
            <label id="login" for="email">Email or phone</label><input id="email" type="email">
            <label for="password">Password</label><input id="password" type="password">
            <button>Sign in</button><button>Sign in with another account</button>
        ''')
        link, _ = first_visible_locator(self.page, SIGN_IN_LOCATORS)
        self.assertEqual(link.evaluate('(element) => element.tagName'), "A")
        submit, _ = first_visible_locator(self.page, SUBMIT_LOCATORS)
        self.assertEqual(submit.evaluate('(element) => element.tagName'), "BUTTON")
        for definitions, value in [(USERNAME_LOCATORS, "test@example.invalid"),
                                   (PASSWORD_LOCATORS, "test-only")]:
            locator, _ = first_visible_locator(self.page, definitions)
            locator.fill(value)
            self.assertEqual(locator.input_value(), value)

    def test_label_alternative(self):
        self.page.set_content('<label>Email<input type="email"></label>')
        locator, _ = first_visible_locator(self.page, USERNAME_LOCATORS)
        locator.fill('test@example.invalid')
        self.assertEqual(locator.input_value(), "test@example.invalid")

    def test_scope_resolves_duplicate_buttons(self):
        self.page.set_content('''
            <button>Sign in</button>
            <section aria-label="Login"><button>Sign in</button></section>
        ''')
        with self.assertRaisesRegex(RuntimeError, "Ambiguous locator"):
            first_visible_locator(self.page, SUBMIT_LOCATORS)
        definition = dict(SUBMIT_LOCATORS[0], scope={
            "strategy": "role", "role": "region", "name": "Login"
        })
        locator, _ = first_visible_locator(self.page, [definition])
        locator.click()
        self.assertEqual(locator.count(), 1)

    def test_hidden_element_is_not_returned(self):
        self.page.set_content('<button style="display:none">Sign in</button>')
        self.assertEqual(
            first_visible_locator(self.page, SUBMIT_LOCATORS, timeout=100, poll_interval=20), (None, None)
        )

if __name__ == "main":
    unittest.main()

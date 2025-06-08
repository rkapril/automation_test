import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("automation.log", mode='w'),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
ACCOUNT_ID = os.getenv("ACCOUNT_ID")
# Replace if not using .env
PASSWORD = os.getenv("PASSWORD")
BASE_URL = "https://aqxtrader.aquariux.com"


class AquariuxTrader:
    """Class to handle Aquariux trading platform automation"""

    def __init__(self, headless=False):
        self.setup_driver(headless)
        self.screenshot_dir = "screenshots"
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.current_instrument_selected = None

    def setup_driver(self, headless=False):
        options = Options()
        options.add_argument("--start-maximized")
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

        service = Service()  # Assumes chromedriver is in PATH
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)  # Default explicit wait
        logger.info("WebDriver initialized")

    def take_screenshot(self, name):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(self.screenshot_dir, f"{name}_{timestamp}.png")
        try:
            self.driver.save_screenshot(filename)
            logger.info(f"Screenshot saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to take screenshot '{name}': {e}")
        return filename

    def _wait_for_element(self, by, value, timeout=15, visible=False, clickable=False):
        custom_wait = WebDriverWait(self.driver, timeout)
        try:
            if clickable:
                return custom_wait.until(EC.element_to_be_clickable((by, value)))
            elif visible:
                return custom_wait.until(EC.visibility_of_element_located((by, value)))
            else:
                return custom_wait.until(EC.presence_of_element_located((by, value)))
        except TimeoutException:
            logger.error(
                f"Timeout ({timeout}s) waiting for element: {by}={value} (Visible: {visible}, Clickable: {clickable})")
            self.take_screenshot(
                f"element_timeout_{value.replace(' ', '_').replace(':', '_').replace('/', '_')}")
            raise
        except Exception as e:
            logger.error(f"Error waiting for element {by}={value}: {e}")
            self.take_screenshot(f"element_error_{value.replace(' ', '_')}")
            raise

    def login(self):
        try:
            self.driver.get(f"{BASE_URL}/web/login")
            logger.info("Opened login page")

            demo_tab = self._wait_for_element(
                By.CSS_SELECTOR, "[data-testid='tab-login-account-type-demo']", clickable=True)
            demo_tab.click()
            logger.info("Selected Demo account tab")

            user_input = self._wait_for_element(
                By.CSS_SELECTOR, "input[data-testid='login-user-id']")
            user_input.send_keys(ACCOUNT_ID)

            pass_input = self._wait_for_element(
                By.CSS_SELECTOR, "input[data-testid='login-password']")
            pass_input.send_keys(PASSWORD)
            logger.info("Entered credentials")
            self.take_screenshot("login_credentials_entered")

            sign_in_btn = self._wait_for_element(
                By.CSS_SELECTOR, "button[data-testid='login-submit']", clickable=True)
            sign_in_btn.click()
            logger.info("Clicked sign in button")

            self._wait_for_element(
                # Longer wait for dashboard
                By.XPATH, "//div[contains(text(), 'Account Balance')]", visible=True, timeout=20)
            logger.info("Login successful!")
            self.take_screenshot("login_successful")
            return True
        except Exception as e:
            self.take_screenshot("login_failure")
            logger.error(f"Login failed: {str(e)}", exc_info=True)
            return False

    def select_instrument(self, instrument_code, retries=3):
        last_exception = None
        for attempt in range(retries):
            try:
                logger.info(
                    f"Attempt {attempt + 1}/{retries} to select instrument: {instrument_code}")

                # Check if already selected
                try:
                    WebDriverWait(self.driver, 3).until(  # Quick check
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div[data-testid='symbol-overview-id']"))
                    )
                    symbol_overview = self.driver.find_element(
                        By.CSS_SELECTOR, "div[data-testid='symbol-overview-id']")
                    if instrument_code in symbol_overview.text:
                        logger.info(
                            f"Instrument {instrument_code} is ALREADY selected (Symbol Overview: {symbol_overview.text}).")
                        self.current_instrument_selected = instrument_code
                        self.take_screenshot(
                            f"instrument_already_selected_{instrument_code}")
                        return True
                except (TimeoutException, NoSuchElementException):
                    logger.info(
                        "Symbol overview not matching or not found, proceeding with selection.")

                search_box = self._wait_for_element(
                    By.CSS_SELECTOR, "input[data-testid='symbol-input-search']", clickable=True, timeout=10)
                search_box.click()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.DELETE)
                search_box.send_keys(instrument_code)
                logger.info(f"Entered '{instrument_code}' in search box")
                self.take_screenshot(
                    f"instrument_search_typed_{instrument_code}")

                # Wait for the "Search Result" header to be visible within the dropdown
                xpath_search_result_header_visibility_check = "//div[@data-testid='symbol-dropdown-result']//div[contains(@class, 'sc-1jx9xug-7') and normalize-space(text())='Search Result']"
                self._wait_for_element(
                    By.XPATH, xpath_search_result_header_visibility_check, timeout=10, visible=True)
                logger.info("'Search Result' header is visible.")
                self.take_screenshot(
                    f"search_result_header_visible_{instrument_code}")

                # Refined XPath for the search result dropdown item
                instrument_item_xpath = (
                    # Anchor to "Search Result" header
                    f"//div[contains(@class, 'sc-1jx9xug-7') and normalize-space(text())='Search Result']"
                    # Get the first "items" container immediately after
                    f"/following-sibling::div[@data-testid='symbol-input-search-items'][1]"
                    # Now, within this container, find the instrument by its specific text structure
                    # Matches the div whose text starts with the instrument code
                    f"//div[contains(@class, 'sc-1jx9xug-5') and normalize-space(starts-with(., '{instrument_code}'))]"
                    # Go up to the main clickable ancestor div for that item
                    f"/ancestor::div[contains(@class, 'sc-1jx9xug-4')][1]"
                )
                logger.info(
                    f"Attempting to find instrument option with XPath: {instrument_item_xpath}")

                instrument_option = self._wait_for_element(
                    By.XPATH, instrument_item_xpath, clickable=True, timeout=15)

                logger.info(
                    f"Found instrument option in dropdown. Text: '{instrument_option.text.strip()[:60]}...'. Clicking it.")

                try:
                    instrument_option.click()
                except ElementClickInterceptedException:
                    logger.warning(
                        "Normal click intercepted, trying JavaScript click for instrument option.")
                    self.driver.execute_script(
                        "arguments[0].click();", instrument_option)

                logger.info(f"Clicked instrument option for {instrument_code}")
                self.take_screenshot(
                    f"instrument_option_clicked_{instrument_code}")

                # Verification
                WebDriverWait(self.driver, 20).until(
                    EC.text_to_be_present_in_element(
                        (By.CSS_SELECTOR, "div[data-testid='symbol-overview-id']"), instrument_code)
                )
                # Additional check: wait for chart to likely not be in a loading state (e.g. spinner gone)
                # This is a placeholder; a more specific "chart loaded" element would be better.
                try:
                    WebDriverWait(self.driver, 5).until_not(
                        # Replace with actual spinner if one exists on chart
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div.spinner-class-placeholder"))
                    )
                except TimeoutException:
                    logger.info(
                        "Chart spinner (placeholder) did not disappear, but proceeding with overview check.")

                self.current_instrument_selected = instrument_code
                logger.info(
                    f"Instrument {instrument_code} selection VERIFIED on chart.")
                self.take_screenshot(
                    f"instrument_{instrument_code}_selected_successfully")
                return True

            except (StaleElementReferenceException, TimeoutException, ElementClickInterceptedException) as e:
                last_exception = e
                error_msg_summary = str(e).splitlines(
                )[0] if str(e) else "No error message"
                logger.warning(
                    f"Attempt {attempt + 1} failed to select instrument '{instrument_code}': {type(e).__name__} - {error_msg_summary}")
                self.take_screenshot(
                    f"select_instrument_attempt_{attempt + 1}_failed_{instrument_code}")
                if attempt < retries - 1:
                    logger.info("Refreshing page and retrying selection...")
                    self.driver.refresh()
                    try:  # Wait for page to be somewhat ready after refresh
                        WebDriverWait(self.driver, 20).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, "input[data-testid='symbol-input-search']"))
                        )
                        logger.info("Page refreshed, search box found.")
                    except TimeoutException:
                        logger.error(
                            "Page did not seem to load correctly after refresh (search box not found).")
                        # Continue to next retry, hoping a subsequent login handles it if session is lost
            except Exception as e:
                last_exception = e
                logger.error(
                    f"Unexpected error during instrument selection '{instrument_code}' (attempt {attempt + 1}): {e}", exc_info=True)
                self.take_screenshot(
                    f"select_instrument_unexpected_error_{instrument_code}")
                break

        self.take_screenshot(
            f"select_instrument_{instrument_code}_failure_final")
        error_type = type(last_exception).__name__ if last_exception else 'N/A'
        error_msg = str(last_exception).splitlines()[
            0] if last_exception else 'No error message'
        logger.error(
            f"Failed to select instrument '{instrument_code}' after {retries} retries. Last error: {error_type} - {error_msg}")
        return False

    # size should be string as it's sent with send_keys
    def set_order_size(self, size="0.01"):
        try:
            size_input = self._wait_for_element(
                By.CSS_SELECTOR, "input[data-testid='trade-input-volume']", clickable=True)
            size_input.click()
            size_input.send_keys(Keys.CONTROL + "a")
            size_input.send_keys(Keys.DELETE)
            size_input.send_keys(str(size))  # Ensure it's a string
            logger.info(f"Set order size to {size}")
            return True
        except Exception as e:
            self.take_screenshot("set_order_size_failure")
            logger.error(f"Failed to set order size: {e}", exc_info=True)
            return False

    def _set_order_parameter(self, input_testid, value_str):  # Use testid directly
        try:
            selector = f"input[data-testid='{input_testid}']"
            input_field = self._wait_for_element(
                By.CSS_SELECTOR, selector, clickable=True)
            input_field.click()
            input_field.send_keys(Keys.CONTROL + "a")
            input_field.send_keys(Keys.DELETE)
            input_field.send_keys(value_str)
            logger.info(f"Set {input_testid} to {value_str}")
            return True
        except Exception as e:
            self.take_screenshot(f"set_parameter_{input_testid}_failure")
            logger.error(
                f"Failed to set parameter {input_testid}: {e}", exc_info=True)
            return False

    def set_stop_loss(self, points=None, price=None):
        if points is not None:
            return self._set_order_parameter('trade-input-stoploss-points', str(points))
        elif price is not None:
            return self._set_order_parameter('trade-input-stoploss-price', str(price))
        logger.warning("No value provided for set_stop_loss")
        return False

    def set_take_profit(self, points=None, price=None):
        if points is not None:
            return self._set_order_parameter('trade-input-takeprofit-points', str(points))
        elif price is not None:
            return self._set_order_parameter('trade-input-takeprofit-price', str(price))
        logger.warning("No value provided for set_take_profit")
        return False

    def _place_order_and_verify(self, order_type, size="0.01", stop_loss_points=None, take_profit_points=None):
        order_side_text = "Buy" if order_type == "buy" else "Sell"
        logger.info(
            f"Attempting to place {order_side_text} order for {self.current_instrument_selected} with size {size}...")

        side_button_xpath = f"//div[@data-testid='trade-button-order-{order_type}']"
        side_button = self._wait_for_element(
            By.XPATH, side_button_xpath, clickable=True)
        side_button.click()
        logger.info(f"Selected {order_side_text} side")

        if not self.set_order_size(str(size)):
            logger.error("Failed to set order size during order placement.")
            return False
        if stop_loss_points is not None and not self.set_stop_loss(points=stop_loss_points):
            logger.error("Failed to set stop loss during order placement.")
            return False
        if take_profit_points is not None and not self.set_take_profit(points=take_profit_points):
            logger.error("Failed to set take profit during order placement.")
            return False

        self.take_screenshot(f"before_place_{order_type}_order_click")
        place_order_button = self._wait_for_element(
            By.XPATH, f"//button[@data-testid='trade-button-order']", clickable=True)
        place_order_button.click()
        logger.info(f"Clicked Place {order_side_text} Order button")
        self.take_screenshot(f"place_{order_type}_order_clicked")

        # Confirmation Dialog
        try:
            confirm_button_xpath = "//button[normalize-space()='Confirm'] | //button/span[normalize-space()='Confirm']"
            confirm_button = self._wait_for_element(
                By.XPATH, confirm_button_xpath, clickable=True, timeout=10)
            logger.info("Confirm button found in dialog. Attempting to click.")
            confirm_button.click()
            logger.info(f"Confirmed {order_side_text} order in dialog")
            self.take_screenshot(f"confirm_{order_type}_dialog_clicked")
        except Exception as e_confirm:  # Catch any exception during confirm
            logger.error(
                f"Error during confirmation dialog for {order_side_text} order: {e_confirm}", exc_info=True)
            self.take_screenshot(f"confirm_{order_type}_dialog_error")
            return False

        notification_found = False
        try:
            self._wait_for_element(
                By.XPATH, "//*[contains(text(), 'Market Order Submitted') or contains(text(), 'Order placed')]", visible=True, timeout=15)
            logger.info(
                f"'Market Order Submitted' notification found for {order_side_text} order.")
            self.take_screenshot(f"{order_type}_order_notification_success")
            notification_found = True
            time.sleep(1)
        except TimeoutException:
            logger.warning(
                f"'Market Order Submitted' notification NOT found for {order_side_text} order. Verifying via positions table.")
            self.take_screenshot(f"{order_type}_order_notification_missed")

        logger.info(f"Verifying {order_side_text} order in positions table...")
        if not self.navigate_to_positions_tab():
            logger.error(
                "Failed to navigate to positions tab for verification.")
            return False

        time.sleep(3.5)  # Increased allow table to update
        open_positions = self.get_open_positions()

        if any(pos['type'] == order_side_text.upper() and pos.get('instrument_for_verification', '').strip() == self.current_instrument_selected for pos in open_positions):
            logger.info(
                f"{order_side_text} order for {self.current_instrument_selected} successfully VERIFIED in positions table.")
            self.take_screenshot(f"{order_type}_order_verified_in_table")
            return True
        else:
            logger.error(
                f"{order_side_text} order for {self.current_instrument_selected} NOT found in positions table. current_instrument_selected: '{self.current_instrument_selected}', Positions: {open_positions}")
            self.take_screenshot(
                f"{order_type}_order_verification_failed_in_table")
            if notification_found:
                logger.warning(
                    "Notification was seen, but order not in table. Potential UI/backend sync issue.")
            return False

    def place_buy_order(self, size="0.01", stop_loss_points=None, take_profit_points=None):
        return self._place_order_and_verify("buy", str(size), stop_loss_points, take_profit_points)

    def place_sell_order(self, size="0.01", stop_loss_points=None, take_profit_points=None):
        return self._place_order_and_verify("sell", str(size), stop_loss_points, take_profit_points)

    def navigate_to_positions_tab(self):
        try:
            tab_container_css = "div.sc-jekbnu-2.dKFAqJ"  # Parent of tabs
            self._wait_for_element(
                By.CSS_SELECTOR, tab_container_css, timeout=10, visible=True)

            positions_tab_css = "div[data-testid='tab-asset-order-type-open-positions']"
            positions_tab = self._wait_for_element(
                By.CSS_SELECTOR, positions_tab_css, clickable=True, timeout=10)

            # Scroll into view if necessary, then click
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", positions_tab)
            time.sleep(0.3)  # Short pause after scroll

            if "selected" not in positions_tab.get_attribute("class").lower():
                positions_tab.click()
                logger.info("Clicked 'Open Positions' tab.")
            else:
                logger.info("'Open Positions' tab was already selected.")

            # Wait for table content to be stable or "no positions" message
            WebDriverWait(self.driver, 15).until(
                EC.any_of(
                    EC.presence_of_element_located(
                        (By.XPATH, "//table[@data-testid='asset-open-table']//thead/tr")),
                    EC.visibility_of_element_located(
                        # Check visibility
                        (By.XPATH, "//div[contains(text(),'No open positions')]")),
                    EC.presence_of_element_located(
                        (By.XPATH, "//table[@data-testid='asset-open-table']//tbody/tr[1]"))
                )
            )
            logger.info(
                "Navigation to 'Open Positions' tab and content load confirmed.")
            self.take_screenshot("navigated_to_positions_tab")
            return True
        except Exception as e:
            self.take_screenshot("navigate_to_positions_tab_failure")
            logger.error(
                f"Failed to navigate to 'Open Positions' tab: {e}", exc_info=True)
            return False

    def get_open_positions(self):  # Removed unused params
        positions = []
        try:
            WebDriverWait(self.driver, 10).until(
                EC.any_of(
                    EC.visibility_of_element_located(
                        (By.XPATH, "//div[contains(text(),'No open positions')]")),
                    EC.presence_of_element_located(
                        (By.XPATH, "//table[@data-testid='asset-open-table']//tbody/tr[1]"))
                )
            )
            try:
                no_positions_message = self.driver.find_element(
                    By.XPATH, "//div[contains(text(),'No open positions')]")
                if no_positions_message.is_displayed():
                    logger.info(
                        "No open positions found on the page (get_open_positions).")
                    self.take_screenshot("no_open_positions_in_get")
                    return []
            except NoSuchElementException:
                pass  # Table should exist

            table_rows = self.driver.find_elements(
                By.XPATH, "//table[@data-testid='asset-open-table']/tbody/tr")
            logger.info(
                f"Found {len(table_rows)} row(s) in 'Open Positions' table.")
            if not table_rows:
                return []

            for row_idx, row_element in enumerate(table_rows):
                try:
                    cols = row_element.find_elements(By.XPATH, "./td | ./th")
                    if not cols:
                        cols = row_element.find_elements(By.TAG_NAME, "td")

                    if len(cols) >= 6:  # Expect OpenDate, OrderNo, Type, P/L, Size, Units
                        open_date_text = cols[0].text.strip()
                        order_no_text = cols[1].text.strip()
                        type_text = cols[2].text.strip().upper()
                        pl_text = cols[3].text.strip()
                        size_text = cols[4].text.strip()
                        units_text = cols[5].text.strip()

                        position_data = {
                            "instrument_for_verification": self.current_instrument_selected,
                            "open_date": open_date_text, "order_no": order_no_text,
                            "type": type_text, "profit_loss": pl_text,
                            "size": size_text, "units": units_text
                        }
                        positions.append(position_data)
                    else:
                        logger.warning(
                            f"Row {row_idx+1} has {len(cols)} columns, expected at least 6. Skipping. HTML: {row_element.get_attribute('outerHTML')[:200]}")
                except StaleElementReferenceException:
                    logger.warning(
                        f"Stale element parsing row {row_idx+1}. Table might have updated. Re-calling get_open_positions might be needed if this persists.")
                    self.take_screenshot(
                        f"stale_row_in_get_open_positions_{row_idx+1}")
                    # For simplicity, we'll skip this row. A more complex retry might involve re-fetching all rows.
                except Exception as e_row:
                    logger.error(
                        f"Error parsing row {row_idx+1} in get_open_positions: {e_row}", exc_info=True)

            logger.info(f"Parsed {len(positions)} positions: {positions}")

        except TimeoutException:
            logger.info(
                "Timeout: 'Open Positions' table/message not found (get_open_positions).")
        except Exception as e:
            logger.error(f"Error getting open positions: {e}", exc_info=True)

        self.take_screenshot("open_positions_parsed_state")
        return positions

    def close_position(self, order_no=None, row_index=0):
        if not self.navigate_to_positions_tab():
            return False
        time.sleep(1)

        try:
            target_description = ""
            close_button_xpath = ""

            if order_no:
                target_description = f"Order No: {order_no}"
                order_row_xpath = f"//table[@data-testid='asset-open-table']//tbody//tr[.//td[contains(text(),'{order_no}')] or .//th[contains(text(),'{order_no}')]]"
                self._wait_for_element(
                    By.XPATH, order_row_xpath, timeout=10, visible=True)
                close_button_xpath = f"{order_row_xpath}//button[contains(translate(normalize-space(), 'CLOSE', 'close'), 'close')]"
            else:
                target_description = f"row index: {row_index}"
                # Ensure row exists before targeting button within it
                self._wait_for_element(
                    By.XPATH, f"(//table[@data-testid='asset-open-table']//tbody/tr)[{row_index + 1}]", timeout=10, visible=True)
                close_button_xpath = f"((//table[@data-testid='asset-open-table']//tbody/tr)//button[contains(translate(normalize-space(), 'CLOSE', 'close'), 'close')])[{row_index + 1}]"

            logger.info(
                f"Attempting to close position by {target_description} using XPath: {close_button_xpath}")
            close_button = self._wait_for_element(
                By.XPATH, close_button_xpath, clickable=True, timeout=10)

            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'auto', block: 'center', inline: 'nearest'});", close_button)
            time.sleep(0.5)
            close_button.click()
            logger.info(f"Clicked 'Close' button for {target_description}")
            self.take_screenshot(
                f"close_button_clicked_for_{order_no if order_no else row_index}")

            confirm_dialog_button_xpath = "//button[normalize-space()='Confirm'] | //button/span[normalize-space()='Confirm']"
            confirm_close_button = self._wait_for_element(
                By.XPATH, confirm_dialog_button_xpath, clickable=True, timeout=10)
            confirm_close_button.click()
            logger.info("Confirmed position closure in dialog.")
            self.take_screenshot("close_confirmed_in_dialog")

            notification_closed = False
            try:
                self._wait_for_element(
                    By.XPATH, "//*[contains(text(), 'Order Closed') or contains(text(), 'Position Closed')]", visible=True, timeout=15)
                logger.info("'Order/Position Closed' notification appeared.")
                notification_closed = True
            except TimeoutException:
                logger.warning(
                    "'Order/Position Closed' notification not found. Relying on table update.")

            time.sleep(3)
            if not self.navigate_to_positions_tab():
                logger.error(
                    "Failed to re-navigate to positions for close verification.")
                return False

            current_positions = self.get_open_positions()
            if order_no:
                if not any(pos['order_no'] == order_no for pos in current_positions):
                    logger.info(
                        f"Order {order_no} successfully removed from positions table.")
                    return True
                else:
                    logger.error(
                        f"Order {order_no} still found in positions table. Positions: {current_positions}")
                    return False
            elif notification_closed:  # No order_no, but notification seen
                logger.info(
                    f"Position at index {row_index} likely closed (notification seen).")
                return True
            # If no order_no and no notification, it's hard to be sure. Could compare counts if needed.
            logger.warning(
                f"Could not definitively verify closure for {target_description} without order_no and no notification.")
            return False  # Less certain in this case

        except Exception as e:
            self.take_screenshot(
                f"close_position_failure_{order_no if order_no else row_index}")
            logger.error(
                f"Failed to close position (Target: {target_description}): {e}", exc_info=True)
            return False

    def bulk_close_positions(self):
        if not self.navigate_to_positions_tab():
            return False
        time.sleep(1.5)

        try:
            if self.driver.find_elements(By.XPATH, "//div[contains(text(),'No open positions') and not(contains(@style,'display: none'))]"):
                logger.info("No open positions to bulk close.")
                return True
            self.take_screenshot("before_bulk_close")

            select_all_xpath = "//table[@data-testid='asset-open-table']//thead//input[@type='checkbox']"
            select_all_checkbox = self._wait_for_element(
                By.XPATH, select_all_xpath, clickable=True, timeout=7)
            if not select_all_checkbox.is_selected():
                self.driver.execute_script(
                    "arguments[0].click();", select_all_checkbox)  # JS click
            logger.info("'Select All' checkbox processed.")
            self.take_screenshot("select_all_checkboxes_processed")

            bulk_close_button = self._wait_for_element(
                By.CSS_SELECTOR, "[data-testid='bulk-close']", clickable=True)
            bulk_close_button.click()
            logger.info("Clicked 'Bulk Close' button.")
            self.take_screenshot("bulk_close_button_clicked")

            confirm_button = self._wait_for_element(
                By.XPATH, "//button[normalize-space()='Confirm']", clickable=True, timeout=10)
            confirm_button.click()
            logger.info("Confirmed bulk close action.")
            self.take_screenshot("bulk_close_confirmed")

            time.sleep(3)
            if not self.navigate_to_positions_tab():
                return False  # Refresh view

            if self.driver.find_elements(By.XPATH, "//div[contains(text(),'No open positions') and not(contains(@style,'display: none'))]") \
               or not self.get_open_positions():
                logger.info("Bulk close successful: No open positions found.")
                self.take_screenshot("bulk_close_success_final")
                return True
            else:
                logger.error(
                    "Bulk close failed or incomplete: Open positions still exist.")
                self.take_screenshot("bulk_close_failure_positions_remain")
                return self.close_all_positions_individually(failed_bulk=True)
        except Exception as e:
            self.take_screenshot("bulk_close_positions_error")
            logger.error(f"Error during bulk close: {e}", exc_info=True)
            # Custom flag
            return self.close_all_positions_individually(failed_bulk_due_to_exception=True)

    def close_all_positions_individually(self, failed_bulk=False, failed_bulk_due_to_exception=False, failed_bulk_due_to_select_all=False):
        log_prefix = "Attempting to close all open positions individually"
        if failed_bulk_due_to_select_all:
            log_prefix += " (Fallback: 'Select All' checkbox issue)."
        elif failed_bulk_due_to_exception:
            log_prefix += " (Fallback: Exception during bulk close)."
        elif failed_bulk:
            log_prefix += " (Fallback: Bulk close left positions)."
        logger.info(log_prefix)

        for i in range(25):  # Max 25 attempts, to prevent infinite loops
            if not self.navigate_to_positions_tab():
                return False
            time.sleep(1.5)

            close_buttons_xpath = "//table[@data-testid='asset-open-table']/tbody/tr//button[contains(translate(normalize-space(), 'CLOSE', 'close'), 'close')]"
            close_buttons = self.driver.find_elements(
                By.XPATH, close_buttons_xpath)

            if not close_buttons:
                logger.info(
                    f"No 'Close' buttons found (attempt {i+1}). Assuming all positions closed.")
                return not self.get_open_positions()  # Final check

            logger.info(
                f"Found {len(close_buttons)} 'Close' button(s). Closing the first one.")
            try:
                first_close_button = close_buttons[0]
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", first_close_button)
                time.sleep(0.5)
                first_close_button.click()

                confirm_button = self._wait_for_element(
                    By.XPATH, "//button[normalize-space()='Confirm']", clickable=True, timeout=10)
                confirm_button.click()
                logger.info("Confirmed individual position closure.")
                time.sleep(2.5)  # Wait for UI to update
            except Exception as e_ind_close:
                logger.error(
                    f"Error closing one position individually: {e_ind_close}", exc_info=True)
                self.take_screenshot(f"individual_close_error_{i}")
                # If one fails, break to avoid repeated failures on a problematic UI state for that item
                # The final check will determine success/failure of overall operation
                break

        logger.info("Finished attempts for individual closures.")
        if not self.navigate_to_positions_tab():
            return False
        return not self.get_open_positions()  # True if no positions left

    def quit(self):
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully.")
            except Exception as e:
                logger.error(f"Error during WebDriver quit: {e}")


def run_test_script(run_headless=False):  # Add run_headless parameter
    # Pass it to the constructor
    trader = AquariuxTrader(headless=run_headless)
    all_tests_passed = True
    try:
        if not trader.login():
            all_tests_passed = False
            raise Exception("Login Failed")

        # Or any other valid, available instrument
        if not trader.select_instrument("DASHUSD.std"):
            all_tests_passed = False
            logger.error("Instrument Selection Failed for DASHUSD.std")
            # Depending on test strategy, you might want to raise an exception or continue
            # For now, we'll let it continue to attempt closing any pre-existing positions if any.

        if trader.current_instrument_selected == "DASHUSD.std":  # Only trade if selection was successful
            logger.info("--- Starting Buy Order Test ---")
            if not trader.place_buy_order(size="0.01", stop_loss_points=2000, take_profit_points=2000):
                logger.error("Buy order placement/verification failed.")
                all_tests_passed = False
            time.sleep(2)

            logger.info("--- Starting Sell Order Test ---")
            if not trader.place_sell_order(size="0.01", stop_loss_points=2000, take_profit_points=2000):
                logger.error("Sell order placement/verification failed.")
                all_tests_passed = False
            time.sleep(2)
        else:
            logger.warning(
                f"Skipping order tests as target instrument DASHUSD.std was not selected. Current: {trader.current_instrument_selected}")

        logger.info("--- Starting Position Closure Test ---")
        if trader.navigate_to_positions_tab():
            initial_positions = trader.get_open_positions()
            if not initial_positions:
                logger.info("No positions to close.")
            elif not trader.close_all_positions_individually():  # Prefer individual close for robustness in tests
                # elif not trader.bulk_close_positions(): # Alternative to test bulk close
                logger.error("Closing positions failed.")
                all_tests_passed = False
        else:
            logger.error("Could not navigate to positions tab for closure.")
            all_tests_passed = False

        if all_tests_passed:
            logger.info("All specific test steps completed successfully!")
        else:
            logger.error("One or more specific test steps failed. Check logs.")

    except Exception as e:
        logger.error(f"Critical error in test script: {e}", exc_info=True)
        if hasattr(trader, 'take_screenshot'):
            trader.take_screenshot("critical_test_SCRIPT_failure")
        all_tests_passed = False
    finally:
        if hasattr(trader, 'take_screenshot'):
            trader.take_screenshot("test_script_FINISH_state")
        logger.info(
            "Test script execution finished. WebDriver will be closed after a pause.")
        time.sleep(5 if not run_headless else 1)  # Use run_headless here
        if hasattr(trader, 'quit'):
            trader.quit()

    return all_tests_passed


if __name__ == "__main__":
    # Define desired headless state here
    execute_headless = False  # Set to True to run headless, False to run with UI

    if not os.getenv("PASSWORD") or os.getenv("PASSWORD") == "your_password_here":
        print("ERROR: PASSWORD environment variable not set or is default. Please set it in a .env file or directly.")
        logger.error(
            "ERROR: PASSWORD environment variable not set or is default.")
    elif run_test_script(run_headless=execute_headless):  # Pass the headless state
        print("Test script: PASSED")
    else:
        print("Test script: FAILED")

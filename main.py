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
                        logging.FileHandler("automation.log", mode='w'),  # Overwrite log file each run
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
ACCOUNT_ID = os.getenv("ACCOUNT_ID", "2092009092")
PASSWORD = os.getenv("PASSWORD", "your_password_here") # <<< --- IMPORTANT: Replace with your actual password or set in .env
BASE_URL = "https://aqxtrader.aquariux.com"


class AquariuxTrader:
    """Class to handle Aquariux trading platform automation"""

    def __init__(self, headless=False):
        self.setup_driver(headless)
        self.screenshot_dir = "screenshots"
        self.current_instrument_selected = None # To track the active instrument

    def setup_driver(self, headless=False):
        options = Options()
        options.add_argument("--start-maximized")
        # options.add_argument("--disable-infobars") # Suppress "Chrome is being controlled"
        # options.add_argument("--disable-extensions")
        # options.add_experimental_option("excludeSwitches", ["enable-automation"]) # Might help with bot detection
        # options.add_experimental_option('useAutomationExtension', False)
        if headless:
            options.add_argument("--headless=new") # Newer headless mode
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            # options.add_argument("--no-sandbox") # Usually for Linux/Docker
            # options.add_argument("--disable-dev-shm-usage") # Usually for Linux/Docker

        service = Service() # Assumes chromedriver is in PATH or use Service(executable_path='/path/to/chromedriver')
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20) # Increased default wait time
        logger.info("WebDriver initialized")

    def take_screenshot(self, name):
        os.makedirs(self.screenshot_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(self.screenshot_dir, f"{name}_{timestamp}.png")
        try:
            self.driver.save_screenshot(filename)
            logger.info(f"Screenshot saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to take screenshot '{name}': {e}")
        return filename

    def _wait_for_element(self, by, value, timeout=15, visible=False, clickable=False):
        """Consolidated wait function."""
        try:
            if clickable:
                return self.wait.until(EC.element_to_be_clickable((by, value)))
            elif visible:
                return self.wait.until(EC.visibility_of_element_located((by, value)))
            else:
                return self.wait.until(EC.presence_of_element_located((by, value)))
        except TimeoutException:
            logger.error(f"Timeout waiting for element: {by}={value}")
            self.take_screenshot(f"element_timeout_{value.replace(' ','_').replace(':','_').replace('/','_')}")
            raise
        except Exception as e:
            logger.error(f"Error waiting for element {by}={value}: {e}")
            self.take_screenshot(f"element_error_{value.replace(' ','_')}")
            raise


    def login(self):
        try:
            self.driver.get(f"{BASE_URL}/web/login")
            logger.info("Opened login page")

            demo_tab = self._wait_for_element(By.CSS_SELECTOR, "[data-testid='tab-login-account-type-demo']", clickable=True)
            demo_tab.click()
            logger.info("Selected Demo account tab")

            user_input = self._wait_for_element(By.CSS_SELECTOR, "input[data-testid='login-user-id']")
            user_input.send_keys(ACCOUNT_ID)

            pass_input = self._wait_for_element(By.CSS_SELECTOR, "input[data-testid='login-password']")
            pass_input.send_keys(PASSWORD)
            logger.info("Entered credentials")
            self.take_screenshot("login_credentials_entered")


            sign_in_btn = self._wait_for_element(By.CSS_SELECTOR, "button[data-testid='login-submit']", clickable=True)
            sign_in_btn.click()
            logger.info("Clicked sign in button")

            self._wait_for_element(By.XPATH, "//div[contains(text(), 'Account Balance')]", visible=True)
            logger.info("Login successful!")
            self.take_screenshot("login_successful")
            return True
        except Exception as e:
            self.take_screenshot("login_failure")
            logger.error(f"Login failed: {str(e)}")
            return False

    def select_instrument(self, instrument_code, retries=3):
        last_exception = None
        for attempt in range(retries):
            try:
                logger.info(f"Attempt {attempt + 1} to select instrument: {instrument_code}")

                # Check if already selected by looking at the current symbol overview
                try:
                    symbol_overview = self._wait_for_element(By.CSS_SELECTOR, "div[data-testid='symbol-overview-id']", timeout=5, visible=True)
                    if instrument_code in symbol_overview.text:
                        logger.info(f"Instrument {instrument_code} is already selected.")
                        self.current_instrument_selected = instrument_code
                        self.take_screenshot(f"instrument_already_selected_{instrument_code}")
                        return True
                except TimeoutException:
                    logger.info("Symbol overview not immediately visible or doesn't match, proceeding with selection.")


                search_box = self._wait_for_element(By.CSS_SELECTOR, "input[data-testid='symbol-input-search']", clickable=True)
                # Reliable clear and send keys
                search_box.click() # Ensure focus
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.DELETE)
                search_box.send_keys(instrument_code)
                logger.info(f"Entered '{instrument_code}' in search box")
                self.take_screenshot(f"instrument_search_{instrument_code}")

                # Wait for search results to populate, looking for a specific testid pattern for the item
                instrument_item_testid = f"symbol-item-{instrument_code.replace('.', '_').lower()}" # Example: symbol-item-dashusd_std
                instrument_item_xpath = f"//div[@data-testid='{instrument_item_testid}'] | //div[contains(@class, 'sc-iubs14-5') and text()='{instrument_code}']" # Fallback if testid isn't exact

                instrument_option = self._wait_for_element(By.XPATH, instrument_item_xpath, clickable=True, timeout=10) # Increased timeout for search results
                logger.info(f"Found instrument option: {instrument_option.text}")
                instrument_option.click()
                logger.info(f"Clicked instrument option for {instrument_code}")

                # Verify selection by checking the main chart's symbol overview
                WebDriverWait(self.driver, 15).until(
                    EC.text_to_be_present_in_element((By.CSS_SELECTOR, "div[data-testid='symbol-overview-id']"), instrument_code)
                )
                self.current_instrument_selected = instrument_code
                logger.info(f"Instrument {instrument_code} selection verified on chart.")
                self.take_screenshot(f"instrument_{instrument_code}_selected")
                return True

            except (StaleElementReferenceException, TimeoutException, ElementClickInterceptedException) as e:
                last_exception = e
                logger.warning(f"Attempt {attempt + 1} failed to select instrument: {e}")
                if attempt < retries - 1:
                    self.take_screenshot(f"select_instrument_retry_attempt_{attempt+1}")
                    logger.info("Refreshing page and retrying...")
                    self.driver.refresh()
                    time.sleep(2) # Wait for refresh to settle
                    if not self.login(): # Re-login might be needed if session is lost
                        logger.error("Re-login failed during instrument selection retry.")
                        return False
                else:
                    logger.error("All retries failed for instrument selection.")
            except Exception as e: # Catch any other unexpected error
                last_exception = e
                logger.error(f"Unexpected error during instrument selection (attempt {attempt+1}): {e}")
                break # Break on truly unexpected errors

        self.take_screenshot(f"select_instrument_{instrument_code}_failure_final")
        logger.error(f"Failed to select instrument '{instrument_code}' after {retries} retries. Last error: {last_exception}")
        return False


    def set_order_size(self, size=0.01):
        try:
            size_input = self._wait_for_element(By.CSS_SELECTOR, "input[data-testid='trade-input-volume']", clickable=True)
            size_input.click() # Ensure focus
            size_input.send_keys(Keys.CONTROL + "a")
            size_input.send_keys(Keys.DELETE)
            size_input.send_keys(str(size))
            logger.info(f"Set order size to {size}")
            return True
        except Exception as e:
            self.take_screenshot("set_order_size_failure")
            logger.error(f"Failed to set order size: {e}")
            return False


    def _set_order_parameter(self, input_css_selector, value_str):
        try:
            input_field = self._wait_for_element(By.CSS_SELECTOR, input_css_selector, clickable=True)
            input_field.click() # Ensure focus
            input_field.send_keys(Keys.CONTROL + "a")
            input_field.send_keys(Keys.DELETE)
            input_field.send_keys(value_str)
            logger.info(f"Set {input_css_selector} to {value_str}")
            return True
        except Exception as e:
            self.take_screenshot(f"set_parameter_{input_css_selector.split('=')[-1].replace(']','').replace('\'', '')}_failure")
            logger.error(f"Failed to set parameter {input_css_selector}: {e}")
            return False

    def set_stop_loss(self, points=None, price=None):
        if points is not None:
            return self._set_order_parameter("[data-testid='trade-input-stoploss-points']", str(points))
        elif price is not None:
            return self._set_order_parameter("[data-testid='trade-input-stoploss-price']", str(price))
        logger.warning("No value provided for set_stop_loss")
        return False

    def set_take_profit(self, points=None, price=None):
        if points is not None:
            return self._set_order_parameter("[data-testid='trade-input-takeprofit-points']", str(points))
        elif price is not None:
            return self._set_order_parameter("[data-testid='trade-input-takeprofit-price']", str(price))
        logger.warning("No value provided for set_take_profit")
        return False


    def _place_order_and_verify(self, order_type, size=0.01, stop_loss_points=None, take_profit_points=None):
        order_side_text = "Buy" if order_type == "buy" else "Sell"
        logger.info(f"Attempting to place {order_side_text} order for {self.current_instrument_selected}...")

        side_button = self._wait_for_element(By.XPATH, f"//div[@data-testid='trade-button-order-{order_type}']", clickable=True)
        side_button.click()
        logger.info(f"Selected {order_side_text} side")

        if not self.set_order_size(size): return False
        if stop_loss_points is not None and not self.set_stop_loss(points=stop_loss_points): return False
        if take_profit_points is not None and not self.set_take_profit(points=take_profit_points): return False

        place_order_button = self._wait_for_element(By.XPATH, f"//button[@data-testid='trade-button-order']", clickable=True)
        place_order_button.click()
        logger.info(f"Clicked Place {order_side_text} Order button")
        self.take_screenshot(f"place_{order_type}_order_clicked")


        confirm_button = self._wait_for_element(By.XPATH, "//button[.//span[contains(text(),'Confirm')]] | //button[contains(text(),'Confirm')]", clickable=True, timeout=10) # More resilient confirm button
        confirm_button.click()
        logger.info(f"Confirmed {order_side_text} order in dialog")
        self.take_screenshot(f"confirm_{order_type}_dialog_clicked")

        # Primary Verification: Check for "Market Order Submitted" notification
        notification_found = False
        try:
            self._wait_for_element(By.XPATH, "//*[contains(text(), 'Market Order Submitted')]", visible=True, timeout=10) # Wait up to 10s
            logger.info(f"'Market Order Submitted' notification found for {order_side_text} order.")
            self.take_screenshot(f"{order_type}_order_notification_success")
            notification_found = True
        except TimeoutException:
            logger.warning(f"'Market Order Submitted' notification NOT found for {order_side_text} order within timeout. Proceeding to verify via positions table.")
            self.take_screenshot(f"{order_type}_order_notification_missed")


        # Secondary/Definitive Verification: Check orders table
        logger.info(f"Verifying {order_side_text} order in positions table...")
        if not self.navigate_to_positions_tab():
            logger.error("Failed to navigate to positions tab for verification.")
            return False

        time.sleep(2) # Allow table to update
        open_positions = self.get_open_positions(expected_instrument=self.current_instrument_selected, expected_type=order_side_text.upper())

        if any(pos['type'] == order_side_text.upper() and self.current_instrument_selected in pos.get('instrument', '') for pos in open_positions): # Check if instrument matches
            logger.info(f"{order_side_text} order for {self.current_instrument_selected} successfully verified in positions table.")
            self.take_screenshot(f"{order_type}_order_verified_in_table")
            return True # Order successfully placed and verified
        else:
            logger.error(f"{order_side_text} order for {self.current_instrument_selected} NOT found in positions table. Positions: {open_positions}")
            self.take_screenshot(f"{order_type}_order_verification_failed_in_table")
            if notification_found:
                 logger.warning("Notification was seen, but order not in table. Potential UI/backend sync issue.")
                 # Depending on strictness, you might still consider this a pass or a flaky pass
            return False


    def place_buy_order(self, size=0.01, stop_loss_points=None, take_profit_points=None):
        return self._place_order_and_verify("buy", size, stop_loss_points, take_profit_points)

    def place_sell_order(self, size=0.01, stop_loss_points=None, take_profit_points=None):
        return self._place_order_and_verify("sell", size, stop_loss_points, take_profit_points)


    def navigate_to_positions_tab(self):
        try:
            # Explicitly wait for the parent container of the tabs to be present
            self._wait_for_element(By.CSS_SELECTOR, "div.sc-jekbnu-2.dKFAqJ", timeout=10)

            # Then find the specific tab
            positions_tab = self._wait_for_element(By.CSS_SELECTOR,
                                                  "div[data-testid='tab-asset-order-type-open-positions']",
                                                  clickable=True)
            # Scroll into view if necessary, useful for smaller viewports or if element is off-screen
            self.driver.execute_script("arguments[0].scrollIntoView(true);", positions_tab)
            time.sleep(0.5) # Small pause after scroll

            positions_tab.click()
            logger.info("Navigated to Open Positions tab")
            # Wait for the table header or empty message to confirm navigation
            WebDriverWait(self.driver, 10).until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//table[@data-testid='asset-open-table']//thead")),
                    EC.presence_of_element_located((By.XPATH, "//div[contains(text(),'No open positions')]"))
                )
            )
            self.take_screenshot("navigated_to_positions_tab")
            return True
        except Exception as e:
            self.take_screenshot("navigate_to_positions_tab_failure")
            logger.error(f"Failed to navigate to Open Positions tab: {e}")
            return False

# In class AquariuxTrader:

    def get_open_positions(self, expected_instrument=None, expected_type=None):
        if not self.navigate_to_positions_tab():
            return []

        positions = []
        try:
            WebDriverWait(self.driver, 10).until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(text(),'No open positions')]")),
                    EC.presence_of_element_located((By.XPATH, "//table[@data-testid='asset-open-table']//tbody/tr[1]"))
                )
            )

            if "No open positions" in self.driver.page_source:
                logger.info("No open positions found on the page.")
                self.take_screenshot("no_open_positions_found_in_get")
                return []

            table_rows = self.driver.find_elements(By.XPATH, "//table[@data-testid='asset-open-table']/tbody/tr")
            logger.info(f"Found {len(table_rows)} row elements in 'Open Positions' table body for parsing.")
            if not table_rows:
                 logger.info("Table body found, but no rows (empty table).")
                 return []

            # Define column indices (0-based) - these are crucial and must match your table structure
            # From your logs, it seems:
            # 0: Open Date
            # 1: Order No. (which might contain instrument if not a separate column)
            # 2: Type (BUY/SELL)
            # 3: Profit/Loss
            # 4: Size
            # 5: Units
            # ... and so on.
            # We are primarily interested in Order No, Type, and "Instrument" (if it exists as a separate column or parsed from Order No.)

            for row_idx, row_element in enumerate(table_rows):
                cols = row_element.find_elements(By.TAG_NAME, "td")
                # Expecting at least 6 columns for basic info
                if len(cols) >= 6:
                    order_no_text = cols[1].text.strip()
                    type_text = cols[2].text.strip()
                    pl_text = cols[3].text.strip()
                    size_text = cols[4].text.strip()
                    units_text = cols[5].text.strip()

                    # Determine the instrument for this row.
                    # If 'expected_instrument' is provided (like from self.current_instrument_selected),
                    # and the 'Order No' column also contains it, we can be more confident.
                    # For general parsing, if there's a dedicated instrument column, parse it.
                    # Otherwise, associate with self.current_instrument_selected if possible or leave as generic.
                    
                    # MODIFIED INSTRUMENT PARSING:
                    # We will assume the instrument for each row is implicitly tied to the
                    # self.current_instrumer_selected when we are *verifying* a placed order.
                    # For general listing, this might need a dedicated "Instrument" column in the table.
                    instrument_for_this_row = self.current_instrument_selected # Default for verification matching

                    # If your table has an "Instrument" column:
                    # Example: //table[@data-testid='asset-open-table']//thead//th[contains(text(), 'Instrument')]
                    # Find its index and use cols[instrument_col_idx].text.strip()
                    # For now, we'll rely on the context of self.current_instrument_selected

                    position_data = {
                        "instrument_for_verification": instrument_for_this_row, # Used for matching during _place_order_and_verify
                        "order_no": order_no_text,
                        "type": type_text,
                        "profit_loss": pl_text,
                        "size": size_text,
                        "units": units_text
                    }
                    logger.info(f"Parsed position (row {row_idx+1}): {position_data}")
                    positions.append(position_data)
                else:
                    logger.warning(f"Skipping row {row_idx+1} from parsing open positions due to insufficient columns: {len(cols)} found.")

        except TimeoutException:
            logger.info("Timeout: No open positions table or 'No open positions' message found within timeout.")
            self.take_screenshot("get_open_positions_timeout_final")
        except Exception as e:
            self.take_screenshot("get_open_positions_error_final")
            logger.error(f"Error getting open positions: {e}", exc_info=True)

        if positions:
            logger.info(f"Successfully parsed {len(positions)} open positions from table.")
        else:
            logger.info("No valid open positions parsed from the table.")
        self.take_screenshot("open_positions_parsed_final_state")
        return positions

    # In _place_order_and_verify method, change the verification line:
    # FROM:
    # if any(pos.get('instrument_from_order_no', '').strip() == self.current_instrument_selected and ...
    # TO:
    # if any(pos.get('instrument_for_verification', '').strip() == self.current_instrument_selected and ...

    def close_position(self, order_no=None, row_index=0):
        if not self.navigate_to_positions_tab(): return False
        time.sleep(1) # Allow table to settle

        try:
            if order_no:
                close_button_xpath = f"//tr[contains(.,'{order_no}')]//button[contains(text(),'Close') or .//span[contains(text(),'Close')]]"
                logger.info(f"Attempting to close order by Order No: {order_no}")
            else:
                # Fallback to row_index if order_no is not specific enough or not provided
                logger.info(f"Attempting to close order by row index: {row_index}")
                # This XPath assumes the 'Close' button is in the last cell (td) of the row. Adjust if structure differs.
                close_button_xpath = f"(//table[@data-testid='asset-open-table']//tbody/tr//button[contains(text(),'Close') or .//span[contains(text(),'Close')]])[{row_index + 1}]" # XPath is 1-indexed

            close_button = self._wait_for_element(By.XPATH, close_button_xpath, clickable=True, timeout=10)
            self.driver.execute_script("arguments[0].scrollIntoView(true);", close_button) # Ensure it's in vie
            time.sleep(0.5)
            close_button.click()
            logger.info(f"Clicked 'Close' button for order {'No: ' + order_no if order_no else 'at index ' + str(row_index)}")
            self.take_screenshot("close_button_clicked")


            confirm_button = self._wait_for_element(By.XPATH, "//button[.//span[contains(text(),'Confirm')]] | //button[contains(text(),'Confirm')]", clickable=True, timeout=10)
            confirm_button.click()
            logger.info("Confirmed position closure in dialog.")
            self.take_screenshot("close_confirmed_in_dialog")


            # Verification: Check for "Order Closed" notification OR the position disappearing
            closed_successfully = False
            try:
                self._wait_for_element(By.XPATH, "//*[contains(text(), 'Order Closed') or contains(text(), 'Position Closed')]", visible=True, timeout=10)
                logger.info("'Order Closed' notification appeared.")
                closed_successfully = True
            except TimeoutException:
                logger.warning("'Order Closed' notification not found. Checking if position is gone from table.")


            # Further verification: ensure the specific order_no is no longer in the table OR total count decreased
            time.sleep(2) # Give table time to update
            self.navigate_to_positions_tab() # Re-navigate to refresh state

            current_positions = self.get_open_positions()
            if order_no:
                if not any(pos['order_no'] == order_no for pos in current_positions):
                    logger.info(f"Order {order_no} successfully removed from positions table.")
                    closed_successfully = True
                else:
                    logger.error(f"Order {order_no} still found in positions table after close attempt.")
                    closed_successfully = False

            elif not closed_successfully and current_positions: # If no specific order_no and notification missed, we can't be sure which one closed
                 logger.warning("Could not definitively verify which position closed without order_no and notification.")


            self.take_screenshot(f"after_close_attempt_order_{order_no if order_no else row_index}")
            return closed_successfully

        except Exception as e:
            self.take_screenshot("close_position_failure")
            logger.error(f"Failed to close position (Order No: {order_no}, Index: {row_index}): {e}", exc_info=True)
            return False


    def bulk_close_positions(self):
        if not self.navigate_to_positions_tab(): return False
        time.sleep(1)

        try:
            # Check if there are any positions to close
            if "No open positions" in self.driver.page_source:
                logger.info("No open positions to bulk close.")
                return True
            self.take_screenshot("before_bulk_close")

            # It's safer to find all individual "Close" buttons if specific checkboxes for bulk actions are problematic
            select_all_checkbox = None
            try:
                select_all_checkbox = self._wait_for_element(By.XPATH, "//table[@data-testid='asset-open-table']//thead//input[@type='checkbox']", clickable=True, timeout=5)
                if select_all_checkbox:
                    select_all_checkbox.click()
                    logger.info("Clicked 'Select All' checkbox for bulk close.")
                    self.take_screenshot("select_all_checkboxes")
                else: # Fallback to clicking individual checkboxes if select all doesn't exist
                    checkboxes = self.driver.find_elements(By.XPATH, "//table[@data-testid='asset-open-table']//tbody//input[@type='checkbox']")
                    if not checkboxes:
                        logger.warning("No individual checkboxes found for positions. Attempting individual close.")
                        return self.close_all_positions_individually()
                    for cb in checkboxes:
                        if not cb.is_selected(): cb.click()
                    logger.info(f"Selected {len(checkboxes)} individual checkboxes.")
                    self.take_screenshot("individual_checkboxes_selected")

            except TimeoutException: # If select-all fails, try individual selection as fallback
                logger.warning("'Select All' checkbox not found. Trying to select individual position checkboxes.")
                checkboxes = self.driver.find_elements(By.XPATH, "//table[@data-testid='asset-open-table']//tbody//input[@type='checkbox']")
                if not checkboxes:
                    logger.warning("No individual checkboxes found for positions after 'Select All' failed. Attempting individual close.")
                    return self.close_all_positions_individually()
                for cb in checkboxes:
                    if not cb.is_selected(): cb.click()
                logger.info(f"Selected {len(checkboxes)} individual checkboxes (fallback).")
                self.take_screenshot("individual_checkboxes_selected_fallback")



            bulk_close_button = self._wait_for_element(By.CSS_SELECTOR, "[data-testid='bulk-close']", clickable=True) # Specific testid is better
            bulk_close_button.click()
            logger.info("Clicked 'Bulk Close' button.")
            self.take_screenshot("bulk_close_button_clicked")


            confirm_button = self._wait_for_element(By.XPATH, "//button[.//span[contains(text(),'Confirm')]] | //button[contains(text(),'Confirm')]", clickable=True, timeout=10)
            confirm_button.click()
            logger.info("Confirmed bulk close action.")
            self.take_screenshot("bulk_close_confirmed")

            # Verification
            time.sleep(2) # Allow UI to update
            self.navigate_to_positions_tab() # Refresh view
            if "No open positions" in self.driver.page_source or not self.get_open_positions(): # Check if table is empty
                logger.info("Bulk close successful: No open positions found.")
                self.take_screenshot("bulk_close_success_final")
                return True
            else:
                logger.error("Bulk close failed or incomplete: Open positions still exist.")
                self.take_screenshot("bulk_close_failure_positions_remain")
                # Optionally, try individual close as a last resort if bulk fails
                logger.info("Attempting to close remaining positions individually after bulk close failed.")
                return self.close_all_positions_individually(failed_bulk=True)


        except Exception as e:
            self.take_screenshot("bulk_close_positions_error")
            logger.error(f"Error during bulk close: {e}", exc_info=True)
            logger.info("Falling back to closing positions individually due to bulk close error.")
            return self.close_all_positions_individually(failed_bulk=True) # Pass a flag


    def close_all_positions_individually(self, failed_bulk=False): # Add a flag
        logger.info("Attempting to close all open positions individually.")
        if failed_bulk:
            logger.info("(This is a fallback after a bulk close attempt failed or was problematic)")

        closed_any = False
        for _ in range(10): # Max attempts to close all, to prevent infinite loop if close fails
            if not self.navigate_to_positions_tab():
                logger.error("Failed to navigate to positions tab in close_all_positions_individually")
                return False # Cannot proceed if cannot navigate

            time.sleep(1) # Let table load

            # Re-fetch close buttons each iteration as DOM changes
            close_buttons = self.driver.find_elements(By.XPATH, "//table[@data-testid='asset-open-table']//tbody//button[contains(text(),'Close') or .//span[contains(text(),'Close')]]")

            if not close_buttons:
                logger.info("No 'Close' buttons found. Assuming all positions are closed.")
                self.take_screenshot("all_positions_closed_individually")
                return True # Success if no close buttons (no positions)

            logger.info(f"Found {len(close_buttons)} 'Close' button(s). Attempting to close the first one.")
            try:
                # Scroll the first button into view and click
                first_close_button = close_buttons[0]
                self.driver.execute_script("arguments[0].scrollIntoView(true);", first_close_button)
                time.sleep(0.5)
                first_close_button.click()
                self.take_screenshot(f"individual_close_button_clicked_{_}")

                confirm_button = self._wait_for_element(By.XPATH, "//button[.//span[contains(text(),'Confirm')]] | //button[contains(text(),'Confirm')]", clickable=True, timeout=10)
                confirm_button.click()
                logger.info("Confirmed individual position closure.")
                self.take_screenshot(f"individual_close_confirmed_{_}")

                # Wait for notification or for the specific position to disappear
                try:
                    self._wait_for_element(By.XPATH, "//*[contains(text(), 'Order Closed') or contains(text(), 'Position Closed')]", visible=True, timeout=7)
                    logger.info("'Order Closed' notification seen for individual close.")
                except TimeoutException:
                    logger.warning("'Order Closed' notification not seen, relying on table update.")
                closed_any = True
                time.sleep(2) # Give UI time to react
            except Exception as e:
                logger.error(f"Error while trying to close a position individually: {e}", exc_info=True)
                self.take_screenshot(f"individual_close_error_{_}")
                # If one close fails, we might want to stop or log and continue
                # For now, we'll let the loop try again or finish if no more buttons
        if closed_any:
             logger.info("Finished attempting individual closures.")
        else:
             logger.warning("No positions were eligible for individual closure attempts (or all failed immediately).")

        # Final verification
        self.navigate_to_positions_tab()
        time.sleep(1)
        final_positions = self.get_open_positions()
        if not final_positions:
            logger.info("All positions successfully closed individually.")
            return True
        else:
            logger.error(f"Failed to close all positions individually. Remaining: {len(final_positions)}")
            self.take_screenshot("individual_close_final_failure")
            return False

    def quit(self):
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully.")
            except Exception as e:
                logger.error(f"Error during WebDriver quit: {e}")
        else:
            logger.info("WebDriver was not initialized or already quit.")


def run_test_script():
    trader = AquariuxTrader(headless=False) # Set True for headless execution
    all_tests_passed = True
    try:
        if not trader.login():
            all_tests_passed = False; raise Exception("Login Failed")

        if not trader.select_instrument("DASHUSD.std"):
            all_tests_passed = False; raise Exception("Instrument Selection Failed")

        logger.info("--- Starting Buy Order Test ---")
        if not trader.place_buy_order(size=0.01, stop_loss_points=200, take_profit_points=200): # Increased SL/TP
            logger.error("Buy order placement or verification failed.")
            all_tests_passed = False
        else:
            logger.info("Buy order test completed.")
        time.sleep(3) # Pause between orders

        logger.info("--- Starting Sell Order Test ---")
        if not trader.place_sell_order(size=0.01, stop_loss_points=200, take_profit_points=200):
            logger.error("Sell order placement or verification failed.")
            all_tests_passed = False
        else:
            logger.info("Sell order test completed.")
        time.sleep(3)

        trader.navigate_to_positions_tab()
        initial_positions = trader.get_open_positions()
        logger.info(f"Positions before closing: {initial_positions}")
        if not initial_positions:
            logger.info("No positions to close, skipping closure tests.")
        else:
            logger.info(f"--- Starting Bulk Close Test ({len(initial_positions)} positions) ---")
            if not trader.bulk_close_positions():
                logger.error("Bulk close positions failed.")
                all_tests_passed = False
            else:
                logger.info("Bulk close positions test completed.")


        if all_tests_passed:
            logger.info("All tests completed successfully!")
        else:
            logger.error("One or more tests failed. Check logs and screenshots.")


    except Exception as e:
        logger.error(f"Critical error in test script: {e}", exc_info=True)
        trader.take_screenshot("critical_test_failure")
        all_tests_passed = False
    finally:
        trader.take_screenshot("test_script_finish_state")
        time.sleep(3)
        trader.quit()
    return all_tests_passed

if __name__ == "__main__":
    if run_test_script():
        print("Test script PASSED")
    else:
        print("Test script FAILED")
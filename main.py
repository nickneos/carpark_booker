import logging
import io
import pandas as pd
import random
import time
from datetime import datetime, timedelta, time

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# # my modules
from my_logger import configure_logger

# constants
URL = "https://gww.condecosoftware.com"
PROFILE_PATH = "/home/nickneos/.mozilla/firefox/uir269rm.selenium"
TIMEOUT_MINUTES = 10
TIMEOUT_SECONDS = 45

# initialise logger
logger = logging.getLogger(__name__)
configure_logger(logger, log_file="carpark_booker.log")


def main(url=URL):

    # initialise webdriver
    options = Options()
    options.add_argument("--headless")
    options.add_argument("-profile")
    options.add_argument(PROFILE_PATH)
    driver = webdriver.Firefox(options=options)

    try:
        # open page
        driver.get(url)

        # webdriverwait
        wait = WebDriverWait(driver, 20)

        # # click login button
        # try:
        #     wait.until(
        #         EC.visibility_of_element_located((By.CSS_SELECTOR, "input#btnRedirectID"))
        #     ).click()
        # except TimeoutException:
        #     pass

        # switch to navigation frame
        switch_frame(driver, "navigation")

        # click on "personal spaces"
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "em.fa-light.fa-lamp-desk"))).click()

        # switch to main frame
        switch_frame(driver, "main")

        # get wanted dates from available dates
        wanted = get_desired_bookings(driver, "dates_wanted.txt")
        logger.info(f"{wanted=}")

        # book each wanted date
        for dte in wanted:
            logger.info(f"searching for {dte} on floor 3")
            make_booking(driver, dte, floor=3)
        for dte in wanted:
            logger.info(f"searching for {dte} on floor 4")
            make_booking(driver, dte, floor=4)

        # close the browser
        driver.close()

    except Exception as e:
        driver.close()
        logger.error(f"{type(e).__name__}: {e}")


def get_my_bookings(driver: webdriver.Firefox) -> list:
    """Gets users existing bookings from condeco.

    Args:
        driver (webdriver.Firefox): Instance of selenium driver.

    Returns:
        list: list of carpark bookings
    """

    # wait for table of bookings
    css_selector = "table#tab_bookingsPanel_tabPanel_deskBookings_welcomeBookedDesksUser"
    wait = WebDriverWait(driver, 30)
    table = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, css_selector)))

    # first table in html to pandas df
    df = pd.read_html(io.StringIO(table.get_attribute("outerHTML")))[0]

    # convert all car park bookings to list
    try:
        bks = df[df["Floor"].str.contains("Car Park")]["From"].to_list()
    except KeyError:
        return []

    return [datetime.strptime(b, "%d/%m/%Y %p") for b in bks]


def get_desired_bookings(driver: webdriver.Firefox, dates_wanted_file: str) -> list:
    """Get a list of car park spots available for the given `days_wanted`.

    Args:
        driver (webdriver.Firefox): Instance of selenium driver.
        dates_wanted_file (str): File with list of dates wanting a booking for.

    Returns:
        list: list of car park spots
    """

    wanted = []
    my_bookings = get_my_bookings(driver)
    dates_desired = parse_dates_file(dates_wanted_file)

    # wait for date selector
    wait = WebDriverWait(driver, 30)
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "select#startDate")))

    # get date selector options
    date_selector = Select(driver.find_element(By.CSS_SELECTOR, "select#startDate"))
    options = [d.text for d in date_selector.options]

    for option in options:
        # date from website will look like "Friday 13 September 2024"
        option_date = datetime.strptime(option, "%A %d %B %Y")

        if option_date in dates_desired and option_date not in my_bookings:
            if option_date.date() == datetime.now().date():
                if datetime.now().time() < time(8, 30):
                    wanted.append(option)
            else:
                wanted.append(option)

    return wanted


def make_booking(driver: webdriver.Firefox, dte: str, floor: int=3) -> bool:
    """Make a booking on the condeco website.

    Args:
        driver (webdriver.Firefox): Instance of selenium driver.
        dte (str): The booking date.
        floor (int, optional): Floor for booking. Defaults to 3.

    Returns:
        bool: True/False if booking was successful.
    """

    # select date
    date_selector = Select(driver.find_element(By.CSS_SELECTOR, "select#startDate"))
    date_selector.select_by_visible_text(dte)

    # tick AM
    AM = driver.find_element(By.CSS_SELECTOR, "input#AM")
    if not AM.is_selected():
        AM.click()

    # tick PM
    PM = driver.find_element(By.CSS_SELECTOR, "input#PM")
    if not PM.is_selected():
        PM.click()

    # select floor
    floor = str(floor)
    floor_selector = Select(driver.find_element(By.CSS_SELECTOR, "select#floorNum"))
    floor_selector.select_by_value(floor)

    # click search
    driver.find_element(By.CSS_SELECTOR, "input#roomSearchButton").click()

    # get results
    wait = WebDriverWait(driver, 20)
    css_selector = "table#tab_bookingsPanel_tabPanel_searchResults_deskSearchResultsGrid"
    results = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, css_selector)))
    cells = results.find_elements(By.CSS_SELECTOR, "td")
    buttons = results.find_elements(By.CSS_SELECTOR, "input[value='Book']")

    # bookings available if a button is present
    if len(buttons) > 0:
        while True:
            # pick a random button (representing a car park spot)
            btn = random.choice(buttons)

            # get the corresponding row of the button
            row = btn.find_element(By.XPATH, "./../..")
            tds = row.find_elements(By.CSS_SELECTOR, "td")

            # get the car park number
            carpark_no = tds[1].text

            # dont want handicap car parks
            if is_disabled_carpark(carpark_no):
                buttons.remove(btn)
                if len(buttons) == 0:
                    logger.warning(f"{dte} - Only available car park is {carpark_no}")
                    return False
                logger.warning(f"{carpark_no} is handicap spot...searching again")

            # click booking button
            else:
                btn.click()
                break

        # confirm booked
        bks = get_my_bookings(driver)
        if datetime.strptime(dte, "%A %d %B %Y") in bks:
            logger.info(f"{dte} - {carpark_no} booked!")
            return True
        else:
            # try again
            logger.warning(f"{dte} - issue booking {carpark_no}...trying again")
            make_booking(driver, dte)

    # no bookings available
    else:
        logger.warning(f"{dte} - [L{floor}] {cells[0].text}")
        return False


def switch_frame(driver: webdriver.Firefox, frame: str):
    """Switch between frames on the website.

    Args:
        driver (webdriver.Firefox): Instance of selenium driver.
        frame (str): Name of the frame to switch to.
    """

    wait = WebDriverWait(driver, 20)

    if frame == "navigation":
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "iframe#leftNavigation")))
        frame = driver.find_element(By.CSS_SELECTOR, "iframe#leftNavigation")
        driver.switch_to.frame(frame)

    elif frame == "main":
        driver.switch_to.parent_frame()
        frame = driver.find_element(By.CSS_SELECTOR, "iframe#mainDisplayFrame")
        driver.switch_to.frame(frame)


def parse_dates_file(filename="exclusions.txt"):
    """Parse the exclusions text file which contains dates to exclude from making bookings.

    Args:
        filename (str, optional): Path of the exclusions text file. Defaults to "exclusions.txt".

    Returns:
        list: Dates parsed from exclusions text file.
    """
    try:
        with open(filename) as f:
            dates = f.readlines()
        return [datetime.strptime(x.strip(), "%Y-%m-%d") for x in dates]
    except FileNotFoundError:
        return []


def is_disabled_carpark(carpark):
    if "disability" in carpark.lower():
        return True
    if "priority" in carpark.lower():
        return True
    return False


if __name__ == "__main__":
    time_start = datetime.now()
    logger.info("starting")

    while True:
        if time_start > datetime.now() - timedelta(seconds=TIMEOUT_SECONDS):
            main()
            wait = 5
            logger.warning(f"Retrying in {wait} seconds")
            time.sleep(wait)
        else:
            logger.warning(f"TIMEOUT_SECONDS ({TIMEOUT_SECONDS}) expired")
            break

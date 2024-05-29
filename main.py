import logging
import io
import pandas as pd
import random
from datetime import datetime

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
DAYS_WANTED = ["Wednesday", "Friday"]
PROFILE_PATH = "/home/nickneos/.mozilla/firefox/kj2737ng.selenium"

# initialise logger
logger = logging.getLogger(__name__)
configure_logger(logger, log_file="carpark_booker.log")


def main(url=URL):
    """
    Return a list of all the available bookings from the `url`

    Args:
    url (string): The url of the website listing the available bookings.
    """

    # initialise webdriver
    options = Options()
    options.add_argument("--headless")
    options.add_argument("-profile")
    options.add_argument(PROFILE_PATH)
    driver = webdriver.Firefox(options=options)

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
    wanted = get_desired_bookings(driver, DAYS_WANTED)

    # book each wanted date
    for dte in wanted:
        make_booking(driver, dte, floor=3)
    for dte in wanted:
        make_booking(driver, dte, floor=4)

    # close the browser
    driver.close()


def get_my_bookings(driver: webdriver.Firefox) -> list:

    # wait for table of bookings
    css_selector = "table#tab_bookingsPanel_tabPanel_deskBookings_welcomeBookedDesksUser"
    wait = WebDriverWait(driver, 30)
    table = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, css_selector)))

    # first table in html to pandas df
    df = pd.read_html(io.StringIO(table.get_attribute("outerHTML")))[0]
    
    # convert all car park bookings to list
    bks = df[df["Floor"].str.contains("Car Park")]["From"].to_list()

    return [datetime.strptime(b, "%d/%m/%Y %p") for b in bks]


def get_desired_bookings(driver: webdriver.Firefox, days_wanted: list) -> list:

    wanted = []
    my_bookings = get_my_bookings(driver)

    # wait for date selector
    wait = WebDriverWait(driver, 30)
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "select#startDate")))

    # get date selector options
    date_selector = Select(driver.find_element(By.CSS_SELECTOR, "select#startDate"))
    options = [d.text for d in date_selector.options]

    for option in options:
        for day in days_wanted:
            if (
                day.lower() in option.lower()
                and datetime.strptime(option, "%A %d %B %Y") not in my_bookings
            ):
                wanted.append(option)

    return wanted


def make_booking(driver: webdriver.Firefox, dte: str, floor: int=3):

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
    results = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "table#tab_bookingsPanel_tabPanel_searchResults_deskSearchResultsGrid")))
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
            if "disability" in carpark_no.lower():
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

    wait = WebDriverWait(driver, 20)

    if frame == "navigation":
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "iframe#leftNavigation")))
        frame = driver.find_element(By.CSS_SELECTOR, "iframe#leftNavigation")
        driver.switch_to.frame(frame)

    elif frame == "main":
        driver.switch_to.parent_frame()
        frame = driver.find_element(By.CSS_SELECTOR, "iframe#mainDisplayFrame")
        driver.switch_to.frame(frame)
        

if __name__ == "__main__":
    main()

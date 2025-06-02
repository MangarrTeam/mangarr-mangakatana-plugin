from plugins.base import MangaPluginBase, Formats, AgeRating, Status, NO_THUMBNAIL_URL
import requests
from datetime import datetime
import pytz
import re
from bs4 import BeautifulSoup
from lxml import etree, html
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

import logging
logger = logging.getLogger(__name__)

class MangaKatanaPlugin(MangaPluginBase):
    languages = ["en"]
    base_url = "https://mangakatana.com"

    def search_manga(self, query:str, language:str=None) -> list[dict]:
        logger.debug(f'Searching for "{query}"')
        try:
            words = re.findall(r"[A-z]*", query)
            filtered_words = [w for w in words if len(w) > 0]
            result = " ".join(filtered_words).lower()

            current_page = 1
            of_pages = 1
            checked_pages = False
            found_mangas = []
            while current_page <= of_pages:
                response = requests.get(f'{self.base_url}/page/{current_page}',
                                            params={
                                                "search": result,
                                                "search_by": "book_name",
                                            },
                                            timeout=10
                                            )
                
                response.raise_for_status()

                if not checked_pages:
                    of_pages = self.get_pages_number_from_html(response.text)
                    checked_pages = True

                found_mangas.append(self.get_manga_list_from_html(response.content))
                current_page += 1

                if current_page <= of_pages:
                    # delay for requesting separate pages
                    time.sleep(2.5)

            return sum(found_mangas, [])

        except Exception as e:
            logger.error(f'Error while searching manga - {e}')

        return []
    
    def get_pages_number_from_html(self, document) -> list[dict]:
        soup = BeautifulSoup(document, 'lxml')
        dom = etree.HTML(str(soup))
        pagesNodes = dom.xpath("//*[@id='book_list']/ul/li")

        if not pagesNodes and len(pagesNodes) < 2:
            return 1

        pagesHtml = etree.tostring(pagesNodes[-2])
        pagesElement = html.fromstring(pagesHtml)
        pages = ''.join(pagesElement.itertext()).strip()

        return int(pages)
    
    def get_manga_list_from_html(self, document) -> list[dict]:
        soup = BeautifulSoup(document, 'lxml')
        dom = etree.HTML(str(soup))
        mangaList = dom.xpath("//*[@id='book_list']/div")

        if not mangaList and len(mangaList) == 0:
            return []
        
        statuses = {
            "ongoing": Status.ONGOING,
            "completed": Status.COMPLETED,
            "cancelled": Status.CANCELLED,
            "hiatus": Status.HIATUS,
        }

        found_mangas = []
        for mangaItem in mangaList:
            manga_dict = self.search_manga_dict()
            urlNode = mangaItem.xpath(".//a[@target='_blank']")[0]
            coverNode = mangaItem.xpath(".//img")[0]
            statusNode = mangaItem.xpath(".//div[contains(@class, 'status')]")[0]
            statusHtml = etree.tostring(statusNode)
            statusElement = html.fromstring(statusHtml)
            status = ''.join(statusElement.itertext()).strip().lower()
            manga_dict["name"] = urlNode.text
            manga_dict["complete"] = (statuses.get(status) or Status.UNKNOWN) == Status.COMPLETED
            manga_dict["cover"] = coverNode.get("src") or NO_THUMBNAIL_URL
            manga_dict["url"] =urlNode.get("href")
            found_mangas.append(manga_dict)

        return found_mangas

    def get_manga(self, arguments:dict) -> dict:
        try:
            url = arguments.get("url")
            if url is None:
                raise Exception("There is no URL in arguments")
            response = requests.get(url,
                                    timeout=10
                                    )
            response.raise_for_status()

            return self.get_manga_from_html(response.text, url, arguments)

        except Exception as e:
            logger.error(f'Error while getting manga - {e}')

        return {}
    
    def get_manga_from_html(self, document, url, arguments) -> dict:
        soup = BeautifulSoup(document, 'lxml')
        dom = etree.HTML(str(soup))
        infoNode = dom.xpath("//*[@class='info']")[0]
        titleNode = infoNode.xpath(".//*[@class='heading']")[0]
        descriptionNode = dom.xpath("//*[@class='summary']/p")[0]
        genresNodes = infoNode.xpath(".//*[@class='genres']/*")
        genres = [genreNode.text for genreNode in genresNodes]

        manga = self.get_manga_dict()
        manga["name"] = titleNode.text
        manga["description"] = " ".join(html.fromstring(etree.tostring(descriptionNode)).itertext())
        manga["original_language"] = "en"
        manga["genres"] = genres
        manga["complete"] = arguments["complete"]
        manga["url"] = url

        return manga
        
    def get_chapters(self, arguments:dict) -> list[dict]:
        try:
            url = arguments.get("url")
            if url is None:
                raise Exception("There is no URL in arguments")
            response = requests.get(url,
                                    timeout=10
                                    )
            response.raise_for_status()

            return self.get_chapters_list_from_html(response.text, arguments)

        except Exception as e:
            logger.error(f'Error while getting chapters - {e}')

        return []
        
    def get_chapters_list_from_html(self, document, arguments) -> list[dict]:
        soup = BeautifulSoup(document, 'lxml')
        dom = etree.HTML(str(soup))
        infoNode = dom.xpath("//*[@class='info']")[0]
        authorsNodes = infoNode.xpath(".//*[@class='author']")
        authors = [authorNode.text for authorNode in authorsNodes]
        chaptersNodes = dom.xpath("//*[@class='chapters']//table//tr")

        chapters = []
        for chapterNode in chaptersNodes:
            chapterTitleNode = chapterNode.xpath(".//div[@class='chapter']/*")[0]
            chapterDateNode = chapterNode.xpath(".//div[@class='update_time']")[0]
            match = re.search(r'Chapter\s+(\d+)', chapterTitleNode.text)


            chapter_dict = self.get_chapter_dict()
            chapter_dict["name"] = str(match.group(1))
            chapter_dict["localization"] = "en"
            dt = datetime.strptime(chapterDateNode.text, "%b-%d-%Y")
            dt_utc = dt.replace(tzinfo=pytz.UTC)
            chapter_dict["release_date"] = dt_utc
            chapter_dict["writer"] = authors
            chapter_dict["penciller"] = chapter_dict["writer"]
            chapter_dict["inker"] = chapter_dict["writer"]
            chapter_dict["colorist"] = chapter_dict["writer"]
            chapter_dict["letterer"] = chapter_dict["writer"]
            chapter_dict["cover_artist"] = chapter_dict["writer"]
            chapter_dict["chapter_number"] = float(chapter_dict["name"])
            chapter_dict["arguments"] = arguments
            chapter_dict["url"] = chapterTitleNode.get("href")
            chapter_dict["source_url"] = chapter_dict["url"]

            chapters.append(chapter_dict)


        return chapters
    
    def get_pages(self, arguments:dict) -> list[dict]:
        try:
            url = arguments.get("url")
            if url is None:
                raise Exception("There is no URL in arguments")
            
            self.driver.set_page_load_timeout(10)
            self.driver.get(url)

            WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, "//*[@id='imgs']//*[contains(@id, 'page')]/img"))
            )
            pages = self.get_pages_list_from_html(self.driver.page_source, arguments)

            self.close_driver()
            
            return pages

        except Exception as e:
            logger.error(f'Error while getting chapters - {e}')

        return []
    
    def get_pages_list_from_html(self, document, arguments) -> list[dict]:
        dom = html.fromstring(document)

        pages = []
        images = dom.xpath("//*[@id='imgs']//*[contains(@id, 'page')]/img")
        for page in images:
            page_dict = self.get_page_dict()
            page_dict["url"] = page.get("data-src")
            pages.append(page_dict)
        
        return pages

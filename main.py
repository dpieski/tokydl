from bs4 import BeautifulSoup
import requests
import os
import ast
from urllib.parse import urljoin, urlparse
import argparse
import sys
import json
from datetime import datetime
import html
from tqdm import tqdm
import time


URLBASE = "https://files02.tokybook.com/audio/"  # file source directory


class AudioBook:
    def __init__(
        self,
        title,
        tags,
        tracklist,
        location,
        properties,
        track_properties=None,
        summary="",
    ):
        self.title = title
        self.tags = tags
        self.tracklist = tracklist
        self.location = location
        self.properties = properties
        self.trackProperties = track_properties
        self.summary = summary

    def save_properties(self):
        self.properties["tags"] = self.tags
        self.properties["track_properties"] = self.trackProperties
        self.properties["save_timestamp"] = str(datetime.now())
        self.properties["summary"] = self.summary
        with open(
            os.path.join(self.location, "properties.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(self.properties, f, ensure_ascii=False, indent=4)


class Series:
    def __init__(
        self,
        title,
        books,
        location,
        properties,
    ):
        self.title = title
        self.books = books
        self.location = location
        self.properties = properties

    def save_properties(self):
        self.properties["title"] = self.title
        self.properties["books"] = self.books
        self.properties["count"] = len(self.books)
        self.properties["save_timestamp"] = str(datetime.now())

        with open(
            os.path.join(self.location, "series.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(self.properties, f, ensure_ascii=False, indent=4)


# Parse the arguments passed via the command line.
def parse_args():
    parser = argparse.ArgumentParser(
        description="This program downloads all the tracks from the given URL."
    )
    parser.add_argument(
        "--book-url", "-b", help="Enter the URL for the book.", type=str, default=""
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Location where folder for the book is created."
        + "Defaults to current directory.",
        type=str,
        default=os.getcwd(),
    )
    parser.add_argument(
        "--series-url",
        "-s",
        help="Enter the URL for the series of books.",
        type=str,
        default="",
    )
    parser.add_argument(
        "--file", "-f", help="File with list of links.", type=str, default=""
    )

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    if not args.book_url and not args.series_url:
        print("Please enter a URL for the Book or Series!")
        parser.print_help(sys.stderr)
        sys.exit(1)

    return args


# Main loop.
def main():
    inputs = parse_args()
    if inputs.file:
        print("Not yet implemented. Please check for an update and try again later.")
        return

    output_folder = inputs.output

    url = inputs.series_url if inputs.series_url else inputs.book_url

    url_path = urlparse(url).path
    path_parts = url_path[1:].split("/")

    print(url)

    url_list = []

    if inputs.series_url:
        if not path_parts[0] == "tag":
            print("You did not enter a 'series' URL.")
            return
        print("Getting Series Information and links....")

        series = get_series(url, output_folder)

        series.save_properties()

        url_list = [books["link"] for books in series.books]
        # print(url_list)
        # time.sleep(5)

    if inputs.book_url:
        if path_parts[0] == "tag":
            print("You entered a 'tag' URL as a book URL.")
            return
        url_list.append(inputs.book_url)

    for bookurl in url_list:
        print("Retrieving book from {}.".format(bookurl))
        soup = parse_url(bookurl)

        book = get_audiobook(soup, output_folder)
        download_audiobook(book)

        book.save_properties()

        print("-------------------------------")
        print("Audiobook Grabbed Successfully!")
        print("-------------------------------")

    print("All Books Grabbed Successfully!")
    print("-------------------------------")


def get_series(url, output_folder):
    books = []
    series_title = ""
    pageFound = True
    pgIDX = 0

    while pageFound:
        pgIDX += 1
        pgURL = urljoin(url + "/", "page/" + str(pgIDX))
        # print(pgURL)

        soup = parse_url(pgURL)
        title = soup.find("title").text

        # Get the series properties from the ld+json section of the page since it is structured data.
        if not series_title:
            series_props = json.loads(
                "".join(soup.find("script", {"type": "application/ld+json"}).contents)
            )
            series_title = get_seriestitle(series_props)

        if "Page not found" in title:
            pageFound = False
        else:
            links = soup.find_all(
                "a",
                {"href": True, "rel": "bookmark"},
            )
            for link in links:
                book = {}
                book["link"] = link["href"]
                book["title"] = link.get_text()
                # print(book)
                books.append(book)

    output_folder = get_outputfolder(output_folder, series_title)

    return Series(
        title=series_title, books=books, properties=series_props, location=output_folder
    )


def download_audiobook(book):
    # loop through the tracks
    track_props = []

    progbar = tqdm(book.tracklist, position=0)
    for track in progbar:
        # for track in tracklist:
        if not track["name"] == "welcome":  # Skip the welcome track
            track_title = track["chapter_link_dropbox"]
            progbar.set_description("Downloading: {}".format(book.title))
            # Clean the URL, maybe use URLENCODE later
            # pg = urljoin(URLBASE, track_title)
            pg = urljoin(URLBASE, track_title.replace("\\", ""))
            track_props.append(
                {
                    "track_number": track["track"],
                    "track_name": track["name"],
                    "track_duration": track["duration"],
                }
            )
            download_file(pg, book.location, track["name"])
    progbar.close()
    print("\nDownload Complete!\n")
    book.trackProperties = track_props
    # create and save the properties file to record the properties of the downloaded audio book.
    # book.save_properties(book)


def get_audiobook(soup, outpath):
    # Get the book properties from the ld+json section of the page since it is structured data.
    book_props = json.loads(
        "".join(soup.find("script", {"type": "application/ld+json"}).contents)
    )

    # Get the book title from the book props. This should be a consistent way to get the book title.
    book_title = get_booktitle(book_props)
    print("Book Title: %s" % book_title)

    # Pull the tags for the book. These could be good for searching later.
    # print(
    #     "Tags: %s"
    #     % soup.find_all("span", {"class": "tags-links"})[0].get_text().strip()[5:]
    # )
    tags = (
        soup.find_all("span", {"class": "tags-links"})[0]
        .get_text()
        .strip()[5:]
        .split(", ")
    )

    texts = soup.find_all("p")
    summary = ""
    pre_skip = True
    for txt in texts:
        para = txt.get_text().strip()
        if "Skip Ads" in para:
            pre_skip = False
            continue
        if "Audiobooks for you!" in para:
            break
        if not pre_skip and para:
            summary = summary + "\n" + para + "\n"

    # print(summary)
    # sys.exit(1)

    # Get the outputFolder - makes the folder, if the default exists, it will increment
    # a number at the end so nothing is written over.
    outputFolder = get_outputfolder(outpath, book_title)

    res = soup.find_all("script")
    # There are a lot of 'script' tags in the page. Loop through them and find the one
    # with the "tracks" list.

    residx = 0
    for idx, script in enumerate(res):
        if "tracks = [" in str(script):
            # print("Index is: {}.".format(idx))
            residx = idx

    trackscript = res[residx]  # get the 'script' tag with the tracks list

    # get the string index starting the list
    trackidx = trackscript.contents[0].find("tracks = [") + 9
    end = trackscript.contents[0].find("]", trackidx) + 1  # find the end of the list

    jsonstring = trackscript.contents[0][trackidx:end].replace(
        "\\n", ""
    )  # get that string of the list

    # convert the string of the list to a real list.
    jsonstring = jsonstring.replace("\\", "")
    tracklist = ast.literal_eval(jsonstring)
    return AudioBook(
        title=book_title,
        tags=tags,
        tracklist=tracklist,
        location=outputFolder,
        properties=book_props,
        summary=summary,
    )


# Parse a particular URL and send files to the outpath.
def parse_url(bookURL):

    # Make sure that the domain passed in is one that we can read. If not, end things.
    domain = urlparse(bookURL).netloc
    if not domain == "tokybook.com":
        print("Please enter a tokybook URL!")
        sys.exit(1)

    # Get the URL page and then parse with BS4
    page = requests.get(bookURL)
    soup = BeautifulSoup(page.content, "html.parser")

    return soup


def get_outputfolder(outpath, dirTitle="audio-", x=0):
    # This should be updated to by a better parse-able folder. Compatible with other services....
    folderpath = os.path.join(
        outpath, (dirTitle + (" " + str(x) if x != 0 else "")).strip()
    )
    if not os.path.exists(folderpath):
        # If it doesn't exist, make the directory
        os.mkdir(folderpath)
        print("Output Path: {}".format(folderpath))
        return folderpath
    else:
        # If it does exist, try again but increase the number at the end.
        return get_outputfolder(outpath, dirTitle, x + 1)


def get_seriestitle(series_props):
    # parse through the book properties to get the book title.
    series_title = ""
    for props in series_props["@graph"]:
        if props["@type"] == "BreadcrumbList":
            crumblist = []
            for prop in props["itemListElement"]:
                crumblist.append(prop["item"]["name"])

            # There are two names in crumblist, [0] = 'Home', [1] = Title - they are 'HTML Safe'
            series_title = html.unescape(crumblist[1])
    return series_title


def get_booktitle(book_props):
    # parse through the book properties to get the book title.
    book_title = ""
    for props in book_props["@graph"]:
        if props["@type"] == "BreadcrumbList":
            crumblist = []
            for prop in props["itemListElement"]:
                crumblist.append(prop["item"]["name"])

            # There are two names in crumblist, [0] = 'Home', [1] = Title - they are 'HTML Safe'
            book_title = html.unescape(crumblist[1])
    return book_title


def download_file(url, outdir, name):
    local_filename = url.split("/")[-1]
    # NOTE the stream=True parameter below
    with requests.get(url, stream=True) as r:
        file_bytes = int(r.headers.get("content-length", 0))
        r.raise_for_status()
        with tqdm.wrapattr(
            open(os.path.join(outdir, local_filename), "wb"),
            "write",
            miniters=1,
            desc="Downloading " + name,
            total=file_bytes,
            position=1,
        ) as f:
            for chunk in r.iter_content(chunk_size=8192):
                # If you have chunk encoded response uncomment if
                # and set chunk_size parameter to None.
                # if chunk:
                f.write(chunk)
    return local_filename


if __name__ == "__main__":
    main()

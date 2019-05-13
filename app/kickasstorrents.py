from urllib.parse import unquote

import aiohttp
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36"  # noqa


async def search(searchterm):
    magnet_links = []
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://kickasstorrents.bz/usearch/{searchterm}/?field=seeders&sorder=desc",
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            data = await resp.text()
    try:
        soup = BeautifulSoup(data, "lxml")
        trs = soup.find("table", {"class": "data"}).find_all("tr")
        for tr in trs:
            try:
                tds = tr.find_all("td")
                seeds = int(tds[3].contents[0])
                title = tds[0].find("a", {"class": "cellMainLink"}).contents[0]
                magnet_link = tds[0].find("a", {"title": "Torrent magnet link"})["href"]
                magnet_link = magnet_link[magnet_link.find("magnet") :]
                magnet_link = unquote(magnet_link)
                magnet_link = unquote(magnet_link)
                if seeds:
                    magnet_links.append(
                        dict(title=title, magnet=magnet_link, seeds=seeds)
                    )
            except Exception as e:
                pass
    except Exception:
        pass
    return magnet_links
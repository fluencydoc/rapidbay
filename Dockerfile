FROM hauxir/libtorrent-python3-ubuntu:latest

RUN apt-get update && \
    apt-get install -y \
    zip \
    ffmpeg \
    git \
    mediainfo

RUN pip install flask
RUN pip install lxml
RUN pip install pymediainfo==4.2.1
RUN pip install iso-639
RUN pip install requests
RUN pip install -e git+https://github.com/agonzalezro/python-opensubtitles#egg=python-opensubtitles
RUN pip install bencodepy
RUN pip install parse-torrent-name
RUN pip install python-dateutil

# BitTorrent incoming
EXPOSE 6881
EXPOSE 6881/udp

# HTTP port
EXPOSE 5000

COPY app /app

WORKDIR /app

CMD python app.py

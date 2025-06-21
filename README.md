A dockerized web gui for executing shell script.

## Installation

Docker compose example:
```
services:
  scriptex:
    container_name: scriptex
    image: safiyu/scriptex:latest
    volumes:
      - /path/to/shellscript:/app/scriptorun.sh:ro
      - /additional/path/based/on/script/:/shared #optional
    environment:
      - TZ=Europe/Paris
      - TRUSTED_IPS=192.168.1.111,192.168.1.222
      - APP_USER=username
      - APP_PASS=password1243
    restart: always
    healthcheck:
      disable: false
    ports:
      - '5100:5100'
```
## Environment Variables

| Variable    | Description                                                               |
|-------------|---------------------------------------------------------------------------|
| TRUSTED_IPS | List of IP's to whitelist. These IP's will be skipped for authentication  |
| APP_USER    | Username                                                                  |
| APP_PASS    | Password                                                                  |

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).

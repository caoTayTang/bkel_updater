#  bkel_updater
This project is to crawl data in my LMS site (HCMUT) and compare with old data. If there any changes, it will use [Discord Webhook](https://discord.com/developers/docs/resources/webhook) to ping to user's server.

## Environment variables
Create a `.env` file includes:
- USER_NAME (LMS username)
- PASSWORD (LMS password)
- LMS_USER_ID (LMS user id, could be found in grades view)
- WEBHOOK_URL (Url of your discord webhook application)

## Feature
- Checking materials in each course if there any changes
- Checking grades in `user>grade`

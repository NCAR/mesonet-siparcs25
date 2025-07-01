import yaml
import requests
import asyncio
from orchestrator import OrchestrateData
from logger import CustomLogger

console = CustomLogger(name="mqtt_logs", log_dir="/cloud/logs")

class Application:
    def __init__(self, ip, topics, port, db_base_url, mb_orch_url, admin_data=None):
        self.orchestrator = OrchestrateData(
            logger=console,
            mb_url=mb_orch_url,
            db_uri=db_base_url,
            topics=topics,
            ip=ip,
            port=port,
            admin_data=admin_data
        )

    async def run(self):
        await self.orchestrator.initialize()
        await self.orchestrator.listen_and_store_readings()

if __name__ == "__main__":
    async def main():
        try:
            with open('/cloud/config.yaml', 'r') as f:
                config = yaml.safe_load(f)

            if not config:
                raise ValueError("Configuration file is empty or not properly formatted.")

            host = config["mqtt"]["host"]
            topics = config["mqtt"]["topics"]
            port = config["mqtt"]["port"]
            db_base_url = config["database_api"]["base_url"]
            mb_orch_url = config["metabase"]["orch_url"]
            admin_data = config["metabase"]["admin_data"]

            app = Application(host, topics, port, db_base_url, mb_orch_url, admin_data)
            await app.run()

        except requests.exceptions.Timeout:
            console.exception("The request timed out")
        except requests.exceptions.ConnectionError as e:
            console.exception(f"Failed to connect to the server: {e}")
        except requests.exceptions.HTTPError as e:
            console.exception(f"HTTP error occurred: {e}")
        except requests.exceptions.JSONDecodeError as e:
            console.exception(f"Response was not valid JSON. {e}")
        except requests.exceptions.RequestException as e:
            console.exception(f"An unexpected request error occurred: {e}")
        except Exception as e:
            console.exception(f"General error occurred: {e}")

    asyncio.run(main())

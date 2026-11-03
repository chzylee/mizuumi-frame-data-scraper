import { configFromEnv, HOST } from "./config";
import { createApp } from "./app";

const config = configFromEnv();
createApp(config).listen(config.port, HOST, (error?: Error) => {
  if (error) throw error;
  console.log(`viewer API on http://${HOST}:${config.port}`);
  console.log(`  data:    ${config.dataDir}`);
  console.log(`  scraped: ${config.scrapedDir}`);
});

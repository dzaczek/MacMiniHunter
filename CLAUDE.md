# MiniHunter Project Notes

## Architecture
- Python scrapers (src/scrapers/) → PostgreSQL → Rust dashboard (dashboard/)
- Docker Compose: db, scraper, dashboard, cloudflared
- Deployed to: dzaczek@10.10.100.22:~/mminihunter
- Dashboard: https://macmini4.hinterdemwald.ch/ (behind Cloudflare Tunnel + Basic Auth)

## Apple Model Numbers (SKUs) - KEY IDENTIFIER
Apple Mac Mini M4 models have unique SKU/Model Numbers that map to exact configs.
Use these for reliable cross-store matching instead of regex title parsing.

### Mac Mini M4 (2024) Swiss Models
- MXK53xx/A = M4, 10c CPU, 10c GPU, 16GB, 256GB
- MXK73xx/A = M4, 10c CPU, 10c GPU, 16GB, 512GB
- MXK93xx/A = M4, 10c CPU, 10c GPU, 24GB, 512GB
- MXKR3xx/A = M4 Pro, 12c CPU, 16c GPU, 24GB, 512GB
- MXLT3xx/A = M4 Pro, 14c CPU, 20c GPU, 24GB, 512GB
- MXLN3xx/A = M4 Pro, 14c CPU, 20c GPU, 48GB, 512GB

The "xx" suffix varies by region (SM = Switzerland). External IDs in stores
often contain these (e.g. "MCYT4SM/A", "MXK53SM/A").

## User Preferences
- Focus: ALL Mac Mini M4 models (not just base configs)
- Smart scraping: traverse + discover, not hardcoded
- Discreet data collection (stealth, delays)
- Dashboard behind auth (no bots/dummy traffic)

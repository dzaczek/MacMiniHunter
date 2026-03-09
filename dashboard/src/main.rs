use actix_web::{dev::ServiceRequest, web, App, Error, HttpResponse, HttpServer};
use actix_web_httpauth::extractors::basic::BasicAuth;
use actix_web_httpauth::middleware::HttpAuthentication;
use chrono::{NaiveDateTime, Utc};
use serde::Serialize;
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use std::cmp::Ordering;
use std::collections::{BTreeSet, HashMap};

struct AuthConfig {
    username: String,
    password: String,
}

async fn basic_auth_validator(
    req: ServiceRequest,
    credentials: BasicAuth,
) -> Result<ServiceRequest, (Error, ServiceRequest)> {
    let auth_config = req
        .app_data::<web::Data<AuthConfig>>()
        .expect("AuthConfig not found");

    let is_valid = credentials.user_id() == auth_config.username
        && credentials.password().is_some_and(|p| p == auth_config.password);

    if is_valid {
        Ok(req)
    } else {
        let response = HttpResponse::Unauthorized()
            .insert_header(("WWW-Authenticate", "Basic realm=\"Mac Mini Hunter\""))
            .finish();
        Err((
            actix_web::error::InternalError::from_response("Unauthorized", response).into(),
            req,
        ))
    }
}

#[derive(Clone, Serialize, sqlx::FromRow)]
struct PriceRow {
    store: String,
    product: String,
    chip: String,
    ram: i32,
    ssd: i32,
    cpu_cores: Option<i32>,
    gpu_cores: Option<i32>,
    price_chf: f64,
    availability: bool,
    is_aggregated: bool,
    scraped_at: NaiveDateTime,
    url: String,
}

#[derive(Clone, Serialize, sqlx::FromRow)]
struct BestDeal {
    product: String,
    store: String,
    price_chf: f64,
    availability: bool,
    is_aggregated: bool,
    scraped_at: NaiveDateTime,
    url: String,
    chip: String,
    ram: i32,
    ssd: i32,
    cpu_cores: Option<i32>,
    gpu_cores: Option<i32>,
}

#[derive(Serialize, sqlx::FromRow)]
struct PricePoint {
    store: String,
    price_chf: f64,
    is_aggregated: bool,
    scraped_at: NaiveDateTime,
}

#[derive(Clone, Serialize, sqlx::FromRow)]
struct HistoricalRow {
    chip: String,
    ram: i32,
    ssd: i32,
    cpu_cores: Option<i32>,
    gpu_cores: Option<i32>,
    store: String,
    price_chf: f64,
    is_aggregated: bool,
    scraped_at: NaiveDateTime,
}

#[derive(Serialize)]
struct SummaryStats {
    total_offers: usize,
    available_offers: usize,
    tracked_configs: usize,
    tracked_stores: usize,
    fresh_stores: usize,
    stale_stores: usize,
    latest_scrape_at: Option<NaiveDateTime>,
}

#[derive(Clone, Serialize)]
struct StoreHealth {
    store: String,
    total_offers: usize,
    available_offers: usize,
    last_scraped_at: NaiveDateTime,
    freshness: String,
    stale_minutes: i64,
}

#[derive(Clone, Serialize)]
struct ConfigInsight {
    key: String,
    config_label: String,
    chip: String,
    ram: i32,
    ssd: i32,
    cpu_cores: Option<i32>,
    gpu_cores: Option<i32>,
    offers: usize,
    available_offers: usize,
    best_price: f64,
    median_price: f64,
    worst_price: f64,
    spread_chf: f64,
    spread_pct: f64,
    best_store: String,
    best_url: String,
}

fn config_key(
    chip: &str,
    ram: i32,
    ssd: i32,
    cpu_cores: Option<i32>,
    gpu_cores: Option<i32>,
) -> String {
    format!(
        "{}|{}|{}|{}|{}",
        chip,
        ram,
        ssd,
        cpu_cores
            .map(|v| v.to_string())
            .unwrap_or_else(|| "na".to_string()),
        gpu_cores
            .map(|v| v.to_string())
            .unwrap_or_else(|| "na".to_string())
    )
}

fn config_label(
    chip: &str,
    ram: i32,
    ssd: i32,
    cpu_cores: Option<i32>,
    gpu_cores: Option<i32>,
) -> String {
    let mut label = format!(
        "{} / {}GB / {}",
        chip,
        ram,
        if ssd >= 1000 {
            format!("{}TB", ssd / 1000)
        } else {
            format!("{}GB", ssd)
        }
    );

    if let (Some(cpu), Some(gpu)) = (cpu_cores, gpu_cores) {
        label.push_str(&format!(" ({cpu}c/{gpu}c)"));
    }

    label
}

fn median(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }

    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(Ordering::Equal));
    let mid = sorted.len() / 2;

    if sorted.len() % 2 == 0 {
        (sorted[mid - 1] + sorted[mid]) / 2.0
    } else {
        sorted[mid]
    }
}

fn compute_summary(latest: &[PriceRow], store_health: &[StoreHealth]) -> SummaryStats {
    let tracked_configs = latest
        .iter()
        .map(|row| config_key(&row.chip, row.ram, row.ssd, row.cpu_cores, row.gpu_cores))
        .collect::<BTreeSet<_>>()
        .len();

    SummaryStats {
        total_offers: latest.len(),
        available_offers: latest.iter().filter(|row| row.availability).count(),
        tracked_configs,
        tracked_stores: store_health.len(),
        fresh_stores: store_health
            .iter()
            .filter(|store| store.freshness == "fresh")
            .count(),
        stale_stores: store_health
            .iter()
            .filter(|store| store.freshness == "stale")
            .count(),
        latest_scrape_at: latest.iter().map(|row| row.scraped_at).max(),
    }
}

fn compute_store_health(latest: &[PriceRow]) -> Vec<StoreHealth> {
    let now = Utc::now().naive_utc();
    let mut grouped: HashMap<String, Vec<PriceRow>> = HashMap::new();

    for row in latest {
        grouped
            .entry(row.store.clone())
            .or_default()
            .push(row.clone());
    }

    let mut stores = grouped
        .into_iter()
        .filter_map(|(store, rows)| {
            let last_scraped_at = rows.iter().map(|row| row.scraped_at).max()?;
            let stale_minutes = (now - last_scraped_at).num_minutes();
            let freshness = if stale_minutes <= 480 {
                "fresh"
            } else if stale_minutes <= 1440 {
                "aging"
            } else {
                "stale"
            };

            Some(StoreHealth {
                store,
                total_offers: rows.len(),
                available_offers: rows.iter().filter(|row| row.availability).count(),
                last_scraped_at,
                freshness: freshness.to_string(),
                stale_minutes,
            })
        })
        .collect::<Vec<_>>();

    stores.sort_by(|a, b| {
        a.stale_minutes
            .cmp(&b.stale_minutes)
            .then_with(|| a.store.cmp(&b.store))
    });
    stores
}

fn compute_config_insights(latest: &[PriceRow]) -> Vec<ConfigInsight> {
    let mut grouped: HashMap<String, Vec<PriceRow>> = HashMap::new();

    for row in latest {
        grouped
            .entry(config_key(
                &row.chip,
                row.ram,
                row.ssd,
                row.cpu_cores,
                row.gpu_cores,
            ))
            .or_default()
            .push(row.clone());
    }

    let mut insights = grouped
        .into_iter()
        .filter_map(|(key, rows)| {
            let first = rows.first()?;
            let mut prices = rows.iter().map(|row| row.price_chf).collect::<Vec<_>>();
            prices.sort_by(|a, b| a.partial_cmp(b).unwrap_or(Ordering::Equal));

            let best_row = rows
                .iter()
                .min_by(|a, b| a.price_chf.partial_cmp(&b.price_chf).unwrap_or(Ordering::Equal))?;
            let best_price = *prices.first()?;
            let worst_price = *prices.last()?;
            let median_price = median(&prices);
            let spread_chf = worst_price - best_price;
            let spread_pct = if worst_price > 0.0 {
                (spread_chf / worst_price) * 100.0
            } else {
                0.0
            };

            Some(ConfigInsight {
                key,
                config_label: config_label(
                    &first.chip,
                    first.ram,
                    first.ssd,
                    first.cpu_cores,
                    first.gpu_cores,
                ),
                chip: first.chip.clone(),
                ram: first.ram,
                ssd: first.ssd,
                cpu_cores: first.cpu_cores,
                gpu_cores: first.gpu_cores,
                offers: rows.len(),
                available_offers: rows.iter().filter(|row| row.availability).count(),
                best_price,
                median_price,
                worst_price,
                spread_chf,
                spread_pct,
                best_store: best_row.store.clone(),
                best_url: best_row.url.clone(),
            })
        })
        .collect::<Vec<_>>();

    insights.sort_by(|a, b| {
        b.spread_chf
            .partial_cmp(&a.spread_chf)
            .unwrap_or(Ordering::Equal)
            .then_with(|| a.config_label.cmp(&b.config_label))
    });
    insights
}

async fn index(pool: web::Data<PgPool>) -> HttpResponse {
    let best_deals: Vec<BestDeal> = sqlx::query_as(
        r#"
        SELECT DISTINCT ON (p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores)
               p.name as product, s.name as store,
               ph.price_chf::float8 as price_chf, ph.availability,
               (pl.url LIKE 'https://www.toppreise.ch/%') as is_aggregated,
               ph.scraped_at::timestamp as scraped_at, pl.url,
               p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores
        FROM price_history ph
        JOIN product_links pl ON ph.link_id = pl.id
        JOIN products p ON pl.product_id = p.id
        JOIN stores s ON pl.store_id = s.id
        WHERE p.chip LIKE 'M4%'
          AND ph.scraped_at = (
              SELECT MAX(ph2.scraped_at) FROM price_history ph2 WHERE ph2.link_id = pl.id
          )
        ORDER BY p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores, ph.availability DESC, ph.price_chf ASC
        "#,
    )
    .fetch_all(pool.get_ref())
    .await
    .unwrap_or_default();

    let latest: Vec<PriceRow> = sqlx::query_as(
        r#"
        SELECT s.name as store, p.name as product,
               p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores,
               ph.price_chf::float8 as price_chf,
               ph.availability,
               (pl.url LIKE 'https://www.toppreise.ch/%') as is_aggregated,
               ph.scraped_at::timestamp as scraped_at, pl.url
        FROM price_history ph
        JOIN product_links pl ON ph.link_id = pl.id
        JOIN products p ON pl.product_id = p.id
        JOIN stores s ON pl.store_id = s.id
        WHERE p.chip LIKE 'M4%'
          AND ph.scraped_at = (
            SELECT MAX(ph2.scraped_at) FROM price_history ph2 WHERE ph2.link_id = pl.id
        )
        ORDER BY p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores, ph.price_chf ASC
        "#,
    )
    .fetch_all(pool.get_ref())
    .await
    .unwrap_or_default();

    let history_rows: Vec<HistoricalRow> = sqlx::query_as(
        r#"
        SELECT p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores,
               s.name as store,
               ph.price_chf::float8 as price_chf,
               (pl.url LIKE 'https://www.toppreise.ch/%') as is_aggregated,
               ph.scraped_at::timestamp as scraped_at
        FROM price_history ph
        JOIN product_links pl ON ph.link_id = pl.id
        JOIN products p ON pl.product_id = p.id
        JOIN stores s ON pl.store_id = s.id
        WHERE p.chip LIKE 'M4%'
          AND ph.scraped_at >= NOW() - INTERVAL '30 days'
        ORDER BY ph.scraped_at ASC
        "#,
    )
    .fetch_all(pool.get_ref())
    .await
    .unwrap_or_default();

    let store_health = compute_store_health(&latest);
    let summary = compute_summary(&latest, &store_health);
    let config_insights = compute_config_insights(&latest);

    let deals_json = serde_json::to_string(&best_deals).unwrap_or_default();
    let latest_json = serde_json::to_string(&latest).unwrap_or_default();
    let history_json = serde_json::to_string(&history_rows).unwrap_or_default();
    let summary_json = serde_json::to_string(&summary).unwrap_or_default();
    let store_health_json = serde_json::to_string(&store_health).unwrap_or_default();
    let config_insights_json = serde_json::to_string(&config_insights).unwrap_or_default();

    let html = format!(
        r##"<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mac Mini Hunter</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
:root {{
  --bg:#0f1115;
  --bg-alt:#171b22;
  --card:#141923;
  --card-strong:#1c2230;
  --line:rgba(255,255,255,.08);
  --text:#eef2ff;
  --muted:#9aa4b2;
  --soft:#cdd6e1;
  --lime:#8df07c;
  --amber:#ffb44d;
  --red:#ff6f61;
  --cyan:#58d4ff;
  --blue:#82a8ff;
  --shadow:0 24px 80px rgba(0,0,0,.35);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:'Space Grotesk',sans-serif;
  color:var(--text);
  background:
    radial-gradient(circle at top left, rgba(88,212,255,.18), transparent 28%),
    radial-gradient(circle at top right, rgba(141,240,124,.14), transparent 30%),
    linear-gradient(180deg, #0b0d12 0%, var(--bg) 38%, #0b0d12 100%);
  min-height:100vh;
}}
a{{color:inherit;text-decoration:none}}
.page{{max-width:1280px;margin:0 auto;padding:28px 20px 48px}}
.hero{{
  display:grid;
  grid-template-columns:1.4fr .9fr;
  gap:18px;
  margin-bottom:18px;
}}
.panel{{
  background:linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.015));
  border:1px solid var(--line);
  border-radius:24px;
  box-shadow:var(--shadow);
  overflow:hidden;
}}
.hero-main{{
  padding:28px;
  position:relative;
  background:
    linear-gradient(135deg, rgba(88,212,255,.12), rgba(255,180,77,.08) 45%, transparent 85%),
    linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.01));
}}
.eyebrow{{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:7px 12px;
  border-radius:999px;
  background:rgba(255,255,255,.05);
  color:var(--soft);
  font-size:.78rem;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.dot{{width:9px;height:9px;border-radius:999px;display:inline-block}}
.dot.ok{{background:var(--lime);box-shadow:0 0 18px rgba(141,240,124,.6)}}
.dot.warn{{background:var(--amber);box-shadow:0 0 18px rgba(255,180,77,.55)}}
.dot.bad{{background:var(--red);box-shadow:0 0 18px rgba(255,111,97,.55)}}
h1{{font-size:clamp(2rem,4vw,4.2rem);line-height:.95;margin:16px 0 12px;max-width:9ch}}
.hero-copy{{color:var(--muted);max-width:58ch;line-height:1.6}}
.hero-meta{{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}}
.chip{{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:10px 14px;
  border-radius:999px;
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.06);
  color:var(--soft);
  font-size:.9rem;
}}
.hero-side{{padding:22px;display:flex;flex-direction:column;gap:14px}}
.stat-grid{{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:12px;
}}
.stat-card{{
  padding:16px;
  border-radius:18px;
  background:var(--card);
  border:1px solid var(--line);
}}
.stat-card .label{{font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}
.stat-card .value{{font-size:2rem;font-weight:700;margin-top:10px}}
.stat-card .hint{{font-size:.88rem;color:var(--muted);margin-top:6px}}
.layout{{
  display:grid;
  grid-template-columns:1.35fr .85fr;
  gap:18px;
  align-items:start;
}}
.stack{{display:flex;flex-direction:column;gap:18px}}
.section{{padding:20px}}
.section-head{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;margin-bottom:16px}}
.section-head h2{{font-size:1.2rem}}
.section-head p{{color:var(--muted);font-size:.92rem}}
.store-grid{{
  display:grid;
  grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));
  gap:12px;
}}
.store-card{{
  padding:16px;
  background:var(--card);
  border:1px solid var(--line);
  border-radius:18px;
}}
.store-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}
.store-name{{font-weight:700}}
.badge{{
  padding:5px 9px;
  border-radius:999px;
  font-size:.72rem;
  letter-spacing:.08em;
  text-transform:uppercase;
  border:1px solid transparent;
}}
.badge.fresh{{background:rgba(141,240,124,.12);color:var(--lime);border-color:rgba(141,240,124,.22)}}
.badge.aging{{background:rgba(255,180,77,.11);color:var(--amber);border-color:rgba(255,180,77,.2)}}
.badge.stale{{background:rgba(255,111,97,.11);color:var(--red);border-color:rgba(255,111,97,.2)}}
.store-metrics{{display:flex;justify-content:space-between;color:var(--muted);font-size:.88rem}}
.insight-list{{display:flex;flex-direction:column;gap:10px}}
.insight-card{{
  padding:16px;
  border-radius:18px;
  border:1px solid var(--line);
  background:linear-gradient(180deg, rgba(130,168,255,.06), rgba(255,255,255,.01));
}}
.insight-card h3{{font-size:1rem;margin-bottom:10px}}
.insight-meta{{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:.9rem}}
.insight-price{{font-size:1.9rem;font-weight:700;margin:8px 0 4px}}
.control-bar{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 20px}}
.toggle{{display:inline-flex;align-items:center;gap:10px;color:var(--soft);font-size:.92rem}}
.toggle input{{accent-color:var(--cyan);width:16px;height:16px}}
.device-grid{{display:grid;grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));gap:12px}}
.device-card{{padding:16px;border-radius:20px;border:1px solid var(--line);background:linear-gradient(180deg, rgba(88,212,255,.05), rgba(255,255,255,.02))}}
.device-card h3{{font-size:1rem;margin-bottom:10px}}
.device-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}}
.device-price{{font-size:1.85rem;font-weight:700;line-height:1}}
.device-change{{font-size:.88rem;font-weight:700}}
.device-change.up{{color:var(--lime)}}
.device-change.down{{color:var(--red)}}
.device-change.flat{{color:var(--muted)}}
.sparkline{{width:100%;height:62px;margin:10px 0 8px;display:block}}
.device-meta{{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:.86rem}}
.device-legend{{display:flex;justify-content:space-between;gap:10px;margin-top:8px;color:var(--muted);font-size:.82rem}}
.pill{{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;font-size:.72rem;background:rgba(255,255,255,.05);color:var(--soft);border:1px solid rgba(255,255,255,.06)}}
.pill.agg{{color:var(--amber);border-color:rgba(255,180,77,.25);background:rgba(255,180,77,.09)}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:18px}}
table{{width:100%;border-collapse:collapse;min-width:760px}}
th,td{{padding:14px 16px;text-align:left;border-bottom:1px solid var(--line)}}
th{{font-size:.76rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:rgba(255,255,255,.03)}}
tr:hover td{{background:rgba(255,255,255,.02)}}
.price{{font-weight:700;color:var(--text);white-space:nowrap}}
.price.good{{color:var(--lime)}}
.price.hot{{color:var(--amber)}}
.mono{{font-family:'IBM Plex Mono',monospace}}
.subtle{{color:var(--muted)}}
.filters{{display:grid;grid-template-columns:repeat(5, minmax(0, 1fr));gap:10px;margin-bottom:14px}}
.filters label{{display:flex;flex-direction:column;gap:6px;font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}
.filters input,.filters select{{
  border:1px solid var(--line);
  background:var(--card);
  color:var(--text);
  border-radius:14px;
  padding:11px 12px;
  font:inherit;
}}
.filters input:focus,.filters select:focus{{outline:none;border-color:rgba(88,212,255,.45)}}
.toolbar{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}}
.toolbar .result{{color:var(--muted);font-size:.92rem}}
.chart-shell{{height:340px;border:1px solid var(--line);border-radius:18px;padding:12px;background:var(--card)}}
.loading{{height:100%;display:grid;place-items:center;color:var(--muted)}}
.status{{display:inline-flex;align-items:center;gap:8px}}
.status .dot{{width:8px;height:8px}}
.deal-row{{cursor:pointer}}
.deal-row.active td{{background:rgba(130,168,255,.08)}}
.inline-chart-row td{{padding:0;background:rgba(255,255,255,.015)}}
.inline-chart-card{{padding:18px}}
.inline-chart-head{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:14px}}
.inline-chart-head h3{{font-size:1.02rem}}
.inline-chart-head p{{color:var(--muted);font-size:.9rem}}
.chart-toolbar{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.chart-mode-group{{display:inline-flex;gap:8px;flex-wrap:wrap}}
.chart-mode-btn{{border:1px solid var(--line);background:rgba(255,255,255,.04);color:var(--soft);border-radius:999px;padding:8px 12px;font:inherit;font-size:.82rem;cursor:pointer;transition:background .18s ease,border-color .18s ease,color .18s ease,transform .18s ease}}
.chart-mode-btn:hover{{background:rgba(255,255,255,.07);transform:translateY(-1px)}}
.chart-mode-btn.active{{background:rgba(88,212,255,.14);border-color:rgba(88,212,255,.38);color:var(--text)}}
.chart-caption{{font-size:.82rem;color:var(--muted)}}
.footer{{padding-top:20px;color:var(--muted);font-size:.9rem;text-align:center}}
@media (max-width: 980px) {{
  .hero,.layout{{grid-template-columns:1fr}}
}}
@media (max-width: 720px) {{
  .page{{padding:16px 14px 36px}}
  .hero-main,.hero-side,.section{{padding:16px}}
  .stat-grid,.filters{{grid-template-columns:1fr 1fr}}
}}
@media (max-width: 560px) {{
  .stat-grid,.filters{{grid-template-columns:1fr}}
  table{{min-width:640px}}
}}
</style>
</head>
<body>
<div class="page">
  <section class="hero">
    <div class="panel hero-main">
      <div class="eyebrow"><span class="dot ok"></span> Swiss Mac Mini market board</div>
      <h1>Price radar for M4 and M4 Pro.</h1>
      <p class="hero-copy">This dashboard focuses on current offers, data quality, and real price spreads across stores. It shows more than the cheapest listing: you can also see how fresh the market is and how wide the spread is for each configuration.</p>
      <div class="hero-meta">
        <span class="chip">Configs tracked: <strong id="hero-configs"></strong></span>
        <span class="chip">Fresh stores: <strong id="hero-fresh"></strong></span>
        <span class="chip">Latest scrape: <strong id="hero-scrape"></strong></span>
      </div>
    </div>
    <aside class="panel hero-side">
      <div class="stat-grid" id="stats"></div>
    </aside>
  </section>

  <div class="layout">
    <main class="stack">
      <section class="panel">
        <div class="control-bar">
          <div>
            <h2>Market Mode</h2>
            <p class="subtle">Use direct scrapers by default, with optional fallback offers from aggregators.</p>
          </div>
          <label class="toggle">
            <input type="checkbox" id="include-aggregated">
            <span>Include aggregated fallback offers</span>
          </label>
        </div>
      </section>

      <section class="panel section">
        <div class="section-head">
          <div>
            <h2>Device Tickers</h2>
            <p>Per-device market cards with current price, 30-day range, and trend sparkline.</p>
          </div>
        </div>
        <div class="device-grid" id="device-stats"></div>
      </section>

      <section class="panel section">
        <div class="section-head">
          <div>
            <h2>Best Deals by Configuration</h2>
            <p>The best current price with spread and availability context.</p>
          </div>
          <p class="subtle">Click a row to view price history for that exact configuration only.</p>
        </div>
        <div class="table-wrap">
          <table id="deals">
            <thead>
              <tr>
                <th>Config</th>
                <th>Best Store</th>
                <th>Best Price</th>
                <th>Spread</th>
                <th>Coverage</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

      <section class="panel section">
        <div class="section-head">
          <div>
            <h2>Live Prices</h2>
            <p>Current prices across all stores with filtering by configuration, status, and name.</p>
          </div>
        </div>
        <div class="filters">
          <label>Search<input id="f-search" type="text" placeholder="Store or product"></label>
          <label>Chip<select id="f-chip"><option value="">All</option></select></label>
          <label>RAM<select id="f-ram"><option value="">All</option></select></label>
          <label>SSD<select id="f-ssd"><option value="">All</option></select></label>
          <label>Status<select id="f-status"><option value="">All</option><option value="available">Available</option><option value="unavailable">Unavailable</option></select></label>
        </div>
        <div class="toolbar">
          <div class="result" id="price-count"></div>
          <div class="result">Auto-refresh every 5 minutes</div>
        </div>
        <div class="table-wrap">
          <table id="prices">
            <thead>
              <tr>
                <th>Status</th>
                <th>Product</th>
                <th>Store</th>
                <th>Price</th>
                <th>Specs</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>
    </main>

    <aside class="stack">
      <section class="panel section">
        <div class="section-head">
          <div>
            <h2>Store Health</h2>
            <p>Shows whether each store is fresh and how many offers it currently contributes.</p>
          </div>
        </div>
        <div class="store-grid" id="store-health"></div>
      </section>

      <section class="panel section">
        <div class="section-head">
          <div>
            <h2>Market Pressure</h2>
            <p>Configurations with the widest price spread across stores.</p>
          </div>
        </div>
        <div class="insight-list" id="insights"></div>
      </section>
    </aside>
  </div>

  <div class="footer">mminihunter dashboard</div>
</div>

<script>
const deals = {deals_json};
const latest = {latest_json};
const historyRows = {history_json};
const summary = {summary_json};
const storeHealth = {store_health_json};
const insights = {config_insights_json};

const fp = value => `CHF ${{value.toFixed(2)}}`;
const formatAgo = value => {{
  const date = new Date(value);
  const now = new Date();
  const minutes = Math.max(0, Math.floor((now - date) / 60000));
  if (minutes < 60) return `${{minutes}}m ago`;
  if (minutes < 1440) return `${{Math.floor(minutes / 60)}}h ago`;
  return `${{Math.floor(minutes / 1440)}}d ago`;
}};
const specLabel = row => {{
  const storage = row.ssd >= 1000 ? `${{row.ssd / 1000}}TB` : `${{row.ssd}}GB`;
  const cores = row.cpu_cores && row.gpu_cores ? ` · ${{row.cpu_cores}}c/${{row.gpu_cores}}c` : '';
  return `${{row.chip}} · ${{row.ram}}GB · ${{storage}}${{cores}}`;
}};
const configKey = row => `${{row.chip}}|${{row.ram}}|${{row.ssd}}|${{row.cpu_cores ?? 'na'}}|${{row.gpu_cores ?? 'na'}}`;
const includeAggregatedInput = document.getElementById('include-aggregated');

function filteredLatestRows() {{
  return latest.filter(row => includeAggregatedInput.checked || !row.is_aggregated);
}}

function computeMarketInsights(rows) {{
  const grouped = new Map();
  rows.forEach(row => {{
    const key = configKey(row);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(row);
  }});

  return [...grouped.entries()].map(([key, items]) => {{
    const sorted = [...items].sort((a, b) => a.price_chf - b.price_chf);
    const prices = sorted.map(item => item.price_chf);
    const mid = Math.floor(prices.length / 2);
    const median = prices.length % 2 === 0 ? (prices[mid - 1] + prices[mid]) / 2 : prices[mid];
    const best = sorted[0];
    const worst = sorted[sorted.length - 1];
    const spread = worst.price_chf - best.price_chf;
    return {{
      key,
      config_label: specLabel(best),
      offers: items.length,
      available_offers: items.filter(item => item.availability).length,
      best_price: best.price_chf,
      best_store: best.store,
      best_url: best.url,
      best_row: best,
      median_price: median,
      worst_price: worst.price_chf,
      spread_chf: spread,
      spread_pct: worst.price_chf > 0 ? (spread / worst.price_chf) * 100 : 0,
    }};
  }}).sort((a, b) => b.spread_chf - a.spread_chf || a.best_price - b.best_price);
}}

function sparklineSvg(points) {{
  if (points.length < 2) return '';
  const width = 240;
  const height = 62;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = Math.max(1, max - min);
  const coords = points.map((value, index) => {{
    const x = (index / (points.length - 1)) * width;
    const y = height - ((value - min) / span) * (height - 8) - 4;
    return `${{index === 0 ? 'M' : 'L'}}${{x.toFixed(1)}},${{y.toFixed(1)}}`;
  }}).join(' ');
  return `
    <svg class="sparkline" viewBox="0 0 ${{width}} ${{height}}" preserveAspectRatio="none">
      <path d="${{coords}}" fill="none" stroke="#58d4ff" stroke-width="2.5" stroke-linecap="round" />
    </svg>
  `;
}}

function buildDeviceStats(rows) {{
  const filteredHistory = historyRows.filter(row => includeAggregatedInput.checked || !row.is_aggregated);
  const byConfig = new Map();

  filteredHistory.forEach(row => {{
    const key = configKey(row);
    if (!byConfig.has(key)) byConfig.set(key, []);
    byConfig.get(key).push(row);
  }});

  return computeMarketInsights(rows).slice(0, 12).map(item => {{
    const series = (byConfig.get(item.key) || [])
      .sort((a, b) => new Date(a.scraped_at) - new Date(b.scraped_at))
      .reduce((acc, row) => {{
        const bucket = row.scraped_at;
        const last = acc[acc.length - 1];
        if (last && last.bucket === bucket) {{
          last.price = Math.min(last.price, row.price_chf);
        }} else {{
          acc.push({{ bucket, price: row.price_chf }});
        }}
        return acc;
      }}, [])
      .map(point => point.price)
      .slice(-20);

    const first = series[0] ?? item.best_price;
    const current = series[series.length - 1] ?? item.best_price;
    const deltaPct = first > 0 ? ((current - first) / first) * 100 : 0;

    return {{
      ...item,
      current_price: current,
      low_30d: series.length ? Math.min(...series) : item.best_price,
      high_30d: series.length ? Math.max(...series) : item.worst_price,
      delta_pct: deltaPct,
      sparkline: sparklineSvg(series),
    }};
  }});
}}

document.getElementById('hero-configs').textContent = summary.tracked_configs;
document.getElementById('hero-fresh').textContent = `${{summary.fresh_stores}} / ${{summary.tracked_stores}}`;
document.getElementById('hero-scrape').textContent = summary.latest_scrape_at ? formatAgo(summary.latest_scrape_at) : 'n/a';

const stats = [
  {{ label: 'Current offers', value: summary.total_offers, hint: 'all stores combined' }},
  {{ label: 'Available now', value: summary.available_offers, hint: 'in-stock offers only' }},
  {{ label: 'Stores tracked', value: summary.tracked_stores, hint: `${{summary.fresh_stores}} fresh / ${{summary.stale_stores}} stale` }},
  {{ label: 'Configurations', value: summary.tracked_configs, hint: 'exact hardware variants' }},
];

document.getElementById('stats').innerHTML = stats.map(card => `
  <article class="stat-card">
    <div class="label">${{card.label}}</div>
    <div class="value">${{card.value}}</div>
    <div class="hint">${{card.hint}}</div>
  </article>
`).join('');

document.getElementById('store-health').innerHTML = storeHealth.map(store => `
  <article class="store-card">
    <div class="store-top">
      <div class="store-name">${{store.store}}</div>
      <span class="badge ${{store.freshness}}">${{store.freshness}}</span>
    </div>
    <div class="store-metrics">
      <span>${{store.available_offers}} / ${{store.total_offers}} live</span>
      <span>${{formatAgo(store.last_scraped_at)}}</span>
    </div>
  </article>
`).join('');

const dealsBody = document.querySelector('#deals tbody');
let expandedRow = null;
let expandedChartRow = null;
let chart = null;
let currentChartMode = 'stores';
const chartHistoryCache = new Map();

function historyKey(deal) {{
  return configKey(deal);
}}

function chartPalette(store) {{
  const colors = {{
    'Apple Store':'#82a8ff',
    'Brack':'#58d4ff',
    'Fust':'#ffb44d',
    'Galaxus':'#8df07c',
    'DQ Solutions':'#b68cff',
    'Tutti':'#ff8d6d',
    'Ricardo':'#ff6f61'
  }};
  return colors[store] || '#cdd6e1';
}}

function normalizeHistoryRows(data) {{
  return data
    .filter(point => includeAggregatedInput.checked || !point.is_aggregated)
    .map(point => ({{
      ...point,
      timestamp: new Date(point.scraped_at),
    }}))
    .sort((a, b) => a.timestamp - b.timestamp);
}}

function buildStoreDatasets(data) {{
  const stores = [...new Set(data.map(point => point.store))];
  return stores.map(store => ({{
    label: store,
    data: data
      .filter(point => point.store === store)
      .map(point => ({{ x: point.timestamp, y: point.price_chf }})),
    borderColor: chartPalette(store),
    backgroundColor: chartPalette(store),
    borderWidth: 2,
    pointRadius: 3,
    pointHoverRadius: 5,
    tension: 0.25,
    fill: false
  }}));
}}

function buildMarketSnapshots(data) {{
  const snapshots = new Map();
  data.forEach(point => {{
    const key = point.timestamp.toISOString();
    const prev = snapshots.get(key);
    if (!prev || point.price_chf < prev.price) {{
      snapshots.set(key, {{ time: point.timestamp, price: point.price_chf }});
    }}
  }});

  return [...snapshots.values()].sort((a, b) => a.time - b.time);
}}

function buildDailyOhlc(data) {{
  const snapshots = buildMarketSnapshots(data);
  const grouped = new Map();

  snapshots.forEach(point => {{
    const day = point.time.toISOString().slice(0, 10);
    if (!grouped.has(day)) grouped.set(day, []);
    grouped.get(day).push(point);
  }});

  return [...grouped.entries()].map(([day, points]) => {{
    const prices = points.map(point => point.price);
    return {{
      day,
      date: new Date(`${{day}}T12:00:00Z`),
      open: points[0].price,
      close: points[points.length - 1].price,
      low: Math.min(...prices),
      high: Math.max(...prices),
    }};
  }});
}}

function chartCaption(mode) {{
  if (mode === 'range') return 'Daily market band based on best available price snapshots.';
  if (mode === 'ohlc') return 'Stock-style daily OHLC view of the best market price.';
  return 'Multi-store line chart for the exact configuration.';
}}

function buildChartConfig(mode, rawData) {{
  const data = normalizeHistoryRows(rawData);
  if (!data.length) return null;

  if (mode === 'range') {{
    const daily = buildDailyOhlc(data);
    return {{
      type: 'line',
      data: {{
        datasets: [
          {{
            label: 'Daily low',
            data: daily.map(point => ({{ x: point.date, y: point.low }})),
            borderColor: 'rgba(88,212,255,0)',
            backgroundColor: 'rgba(88,212,255,.18)',
            pointRadius: 0,
            fill: false
          }},
          {{
            label: 'Daily high',
            data: daily.map(point => ({{ x: point.date, y: point.high }})),
            borderColor: 'rgba(88,212,255,.45)',
            backgroundColor: 'rgba(88,212,255,.18)',
            pointRadius: 0,
            borderWidth: 1.5,
            fill: '-1',
            tension: 0.2
          }},
          {{
            label: 'Close',
            data: daily.map(point => ({{ x: point.date, y: point.close }})),
            borderColor: '#8df07c',
            backgroundColor: '#8df07c',
            borderWidth: 2.4,
            pointRadius: 2,
            pointHoverRadius: 4,
            tension: 0.22,
            fill: false
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
          legend: {{ labels: {{ color: '#cdd6e1' }} }},
          tooltip: {{
            callbacks: {{
              label: context => `${{context.dataset.label}}: CHF ${{context.parsed.y.toFixed(2)}}`
            }}
          }}
        }},
        scales: {{
          x: {{
            type: 'time',
            time: {{ unit: 'day', tooltipFormat: 'PP' }},
            ticks: {{ color: '#9aa4b2' }},
            grid: {{ color: 'rgba(255,255,255,.07)' }}
          }},
          y: {{
            ticks: {{
              color: '#9aa4b2',
              callback: value => `CHF ${{value}}`
            }},
            grid: {{ color: 'rgba(255,255,255,.07)' }}
          }}
        }}
      }}
    }};
  }}

  if (mode === 'ohlc') {{
    const daily = buildDailyOhlc(data);
    const bodyColors = daily.map(point => point.close >= point.open ? '#8df07c' : '#ff6f61');
    return {{
      type: 'bar',
      data: {{
        datasets: [
          {{
            type: 'bar',
            label: 'Range',
            data: daily.map(point => ({{ x: point.date, y: [point.low, point.high] }})),
            backgroundColor: 'rgba(130,168,255,.18)',
            borderColor: 'rgba(130,168,255,.45)',
            borderWidth: 1,
            borderSkipped: false,
            barPercentage: 0.18,
            categoryPercentage: 0.9,
            order: 3
          }},
          {{
            type: 'bar',
            label: 'Open / Close',
            data: daily.map(point => ({{ x: point.date, y: [Math.min(point.open, point.close), Math.max(point.open, point.close)] }})),
            backgroundColor: bodyColors,
            borderColor: bodyColors,
            borderWidth: 1,
            borderSkipped: false,
            barPercentage: 0.52,
            categoryPercentage: 0.9,
            order: 2
          }},
          {{
            type: 'line',
            label: 'Close',
            data: daily.map(point => ({{ x: point.date, y: point.close }})),
            borderColor: '#eef2ff',
            backgroundColor: '#eef2ff',
            borderWidth: 1.5,
            pointRadius: 2,
            pointHoverRadius: 4,
            tension: 0,
            fill: false,
            order: 1
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
          legend: {{ labels: {{ color: '#cdd6e1' }} }},
          tooltip: {{
            callbacks: {{
              afterBody: items => {{
                const idx = items?.[0]?.dataIndex;
                const point = daily[idx];
                if (!point) return '';
                return [
                  `Open: CHF ${{point.open.toFixed(2)}}`,
                  `High: CHF ${{point.high.toFixed(2)}}`,
                  `Low: CHF ${{point.low.toFixed(2)}}`,
                  `Close: CHF ${{point.close.toFixed(2)}}`
                ];
              }}
            }}
          }}
        }},
        scales: {{
          x: {{
            type: 'time',
            time: {{ unit: 'day', tooltipFormat: 'PP' }},
            ticks: {{ color: '#9aa4b2' }},
            grid: {{ color: 'rgba(255,255,255,.07)' }}
          }},
          y: {{
            ticks: {{
              color: '#9aa4b2',
              callback: value => `CHF ${{value}}`
            }},
            grid: {{ color: 'rgba(255,255,255,.07)' }}
          }}
        }}
      }}
    }};
  }}

  return {{
    type: 'line',
    data: {{
      datasets: buildStoreDatasets(data)
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ labels: {{ color: '#cdd6e1' }} }},
        tooltip: {{
          callbacks: {{
            label: context => `${{context.dataset.label}}: CHF ${{context.parsed.y.toFixed(2)}}`
          }}
        }}
      }},
      scales: {{
        x: {{
          type: 'time',
          time: {{ unit: 'day', tooltipFormat: 'PPp' }},
          ticks: {{ color: '#9aa4b2' }},
          grid: {{ color: 'rgba(255,255,255,.07)' }}
        }},
        y: {{
          ticks: {{
            color: '#9aa4b2',
            callback: value => `CHF ${{value}}`
          }},
          grid: {{ color: 'rgba(255,255,255,.07)' }}
        }}
      }}
    }}
  }};
}}

function activateChartMode(chartRow, mode) {{
  chartRow.querySelectorAll('.chart-mode-btn').forEach(button => {{
    button.classList.toggle('active', button.dataset.mode === mode);
  }});
  const caption = chartRow.querySelector('.chart-caption');
  if (caption) caption.textContent = chartCaption(mode);
}}

function renderExpandedChart(chartRow, rawData, mode) {{
  const shell = chartRow.querySelector('.chart-shell');
  const config = buildChartConfig(mode, rawData);
  activateChartMode(chartRow, mode);

  if (!config) {{
    shell.innerHTML = '<div class="loading">No history available for this view.</div>';
    if (chart) {{
      chart.destroy();
      chart = null;
    }}
    return;
  }}

  shell.innerHTML = '<canvas></canvas>';
  const ctx = shell.querySelector('canvas');
  if (chart) chart.destroy();
  chart = new Chart(ctx, config);
}}

function renderDeviceStats(rows) {{
  const cards = buildDeviceStats(rows);
  document.getElementById('device-stats').innerHTML = cards.map(item => {{
    const changeClass = item.delta_pct < -0.1 ? 'up' : item.delta_pct > 0.1 ? 'down' : 'flat';
    const changeLabel = `${{item.delta_pct >= 0 ? '+' : ''}}${{item.delta_pct.toFixed(1)}}%`;
    return `
      <article class="device-card">
        <div class="device-top">
          <div>
            <h3>${{item.config_label}}</h3>
            <div class="device-price">${{fp(item.current_price)}}</div>
          </div>
          <div class="device-change ${{changeClass}}">${{changeLabel}}</div>
        </div>
        ${{item.sparkline}}
        <div class="device-meta">
          <span>Best: ${{item.best_store}}</span>
          <span>${{item.available_offers}} / ${{item.offers}} live</span>
        </div>
        <div class="device-legend">
          <span>30d low ${{fp(item.low_30d)}}</span>
          <span>30d high ${{fp(item.high_30d)}}</span>
        </div>
      </article>
    `;
  }}).join('');
}}

function renderInsights(rows) {{
  document.getElementById('insights').innerHTML = computeMarketInsights(rows).slice(0, 6).map(item => `
    <article class="insight-card">
      <h3>${{item.config_label}}</h3>
      <div class="insight-meta">
        <span>${{item.available_offers}} / ${{item.offers}} available</span>
        <span>${{item.best_store}} leads</span>
      </div>
      <div class="insight-price">${{fp(item.best_price)}}</div>
      <div class="insight-meta">
        <span>median ${{fp(item.median_price)}}</span>
        <span>spread ${{fp(item.spread_chf)}} · ${{item.spread_pct.toFixed(1)}}%</span>
      </div>
    </article>
  `).join('');
}}

function renderDeals() {{
  const rows = filteredLatestRows();
  const insightsMap = new Map(computeMarketInsights(rows).map(item => [item.key, item]));
  dealsBody.innerHTML = '';
  if (expandedChartRow) {{
    expandedChartRow.remove();
    expandedChartRow = null;
  }}
  if (expandedRow) {{
    expandedRow.classList.remove('active');
    expandedRow = null;
  }}
  if (chart) {{
    chart.destroy();
    chart = null;
  }}

  [...insightsMap.values()]
    .sort((a, b) => a.best_price - b.best_price || b.available_offers - a.available_offers)
    .forEach(item => {{
      const deal = item.best_row;
      const row = document.createElement('tr');
      row.className = 'deal-row';
      row.innerHTML = `
        <td>
          <div>${{item.config_label}}</div>
          <div class="subtle mono">${{deal.product}}</div>
        </td>
        <td>${{deal.store}}${{deal.is_aggregated ? ' <span class="pill agg">aggregated</span>' : ''}}</td>
        <td class="price good">${{fp(deal.price_chf)}}</td>
        <td>${{fp(item.spread_chf)}} · ${{item.spread_pct.toFixed(1)}}%</td>
        <td>${{item.available_offers}} / ${{item.offers}} live</td>
        <td>
          <span class="status">
            <span class="dot ${{deal.availability ? 'ok' : 'bad'}}"></span>
            <span>${{deal.availability ? 'available' : 'unavailable'}} · ${{formatAgo(deal.scraped_at)}}</span>
          </span>
        </td>
      `;
      row.addEventListener('click', () => loadChart(deal, row));
      dealsBody.appendChild(row);
    }});

  renderInsights(rows);
  renderDeviceStats(rows);
}}

const fSearch = document.getElementById('f-search');
const fChip = document.getElementById('f-chip');
const fRam = document.getElementById('f-ram');
const fSsd = document.getElementById('f-ssd');
const fStatus = document.getElementById('f-status');

[...new Set(latest.map(row => row.chip))].sort().forEach(value => {{
  fChip.innerHTML += `<option value="${{value}}">${{value}}</option>`;
}});
[...new Set(latest.map(row => row.ram))].sort((a, b) => a - b).forEach(value => {{
  fRam.innerHTML += `<option value="${{value}}">${{value}}GB</option>`;
}});
[...new Set(latest.map(row => row.ssd))].sort((a, b) => a - b).forEach(value => {{
  const label = value >= 1000 ? `${{value / 1000}}TB` : `${{value}}GB`;
  fSsd.innerHTML += `<option value="${{value}}">${{label}}</option>`;
}});

const pricesBody = document.querySelector('#prices tbody');
function renderPrices() {{
  const search = fSearch.value.trim().toLowerCase();
  const chip = fChip.value;
  const ram = fRam.value;
  const ssd = fSsd.value;
  const status = fStatus.value;

  let rows = filteredLatestRows();
  if (search) {{
    rows = rows.filter(row =>
      row.product.toLowerCase().includes(search) ||
      row.store.toLowerCase().includes(search)
    );
  }}
  if (chip) rows = rows.filter(row => row.chip === chip);
  if (ram) rows = rows.filter(row => row.ram === Number(ram));
  if (ssd) rows = rows.filter(row => row.ssd === Number(ssd));
  if (status === 'available') rows = rows.filter(row => row.availability);
  if (status === 'unavailable') rows = rows.filter(row => !row.availability);

  rows.sort((a, b) => {{
    if (a.availability !== b.availability) return Number(b.availability) - Number(a.availability);
    if (a.price_chf !== b.price_chf) return a.price_chf - b.price_chf;
    return new Date(b.scraped_at) - new Date(a.scraped_at);
  }});

  document.getElementById('price-count').textContent = `${{rows.length}} offers visible`;
  pricesBody.innerHTML = rows.map(row => `
    <tr>
      <td>
        <span class="status">
          <span class="dot ${{row.availability ? 'ok' : 'bad'}}"></span>
          <span>${{row.availability ? 'available' : 'unavailable'}}</span>
        </span>
      </td>
      <td><a href="${{row.url}}" target="_blank" rel="noreferrer">${{row.product}}</a></td>
      <td>${{row.store}}</td>
      <td class="price ${{row.price_chf <= 999 ? 'good' : row.price_chf <= 1499 ? '' : 'hot'}}">${{fp(row.price_chf)}}</td>
      <td class="subtle">${{specLabel(row)}}</td>
      <td class="mono subtle">${{formatAgo(row.scraped_at)}}</td>
    </tr>
  `).join('');
}}

[fSearch, fChip, fRam, fSsd, fStatus].forEach(input => {{
  input.addEventListener('input', renderPrices);
  input.addEventListener('change', renderPrices);
}});
includeAggregatedInput.addEventListener('change', () => {{
  renderDeals();
  renderPrices();
}});
renderDeals();
renderPrices();

async function loadChart(deal, rowElement) {{
  if (expandedRow === rowElement && expandedChartRow) {{
    expandedRow.classList.remove('active');
    expandedChartRow.remove();
    expandedRow = null;
    expandedChartRow = null;
    if (chart) {{
      chart.destroy();
      chart = null;
    }}
    return;
  }}

  if (expandedRow) expandedRow.classList.remove('active');
  if (expandedChartRow) expandedChartRow.remove();
  if (chart) {{
    chart.destroy();
    chart = null;
  }}

  rowElement.classList.add('active');
  expandedRow = rowElement;

  const chartRow = document.createElement('tr');
  chartRow.className = 'inline-chart-row';
  chartRow.innerHTML = `
    <td colspan="6">
      <div class="inline-chart-card">
        <div class="inline-chart-head">
          <div>
            <h3>Price History · ${{specLabel(deal)}}</h3>
            <p>${{deal.store}} currently leads at ${{fp(deal.price_chf)}}</p>
          </div>
          <div class="chart-toolbar">
            <div class="chart-mode-group">
              <button class="chart-mode-btn active" type="button" data-mode="stores">Stores</button>
              <button class="chart-mode-btn" type="button" data-mode="range">Range</button>
              <button class="chart-mode-btn" type="button" data-mode="ohlc">OHLC</button>
            </div>
            <div class="chart-caption">${{chartCaption(currentChartMode)}}</div>
          </div>
        </div>
        <div class="chart-shell"><div class="loading">Loading history…</div></div>
      </div>
    </td>
  `;
  rowElement.insertAdjacentElement('afterend', chartRow);
  expandedChartRow = chartRow;

  chartRow.querySelectorAll('.chart-mode-btn').forEach(button => {{
    button.addEventListener('click', () => {{
      currentChartMode = button.dataset.mode;
      const cached = chartHistoryCache.get(historyKey(deal));
      if (cached && expandedChartRow === chartRow) {{
        renderExpandedChart(chartRow, cached, currentChartMode);
      }}
    }});
  }});

  const params = new URLSearchParams({{
    chip: deal.chip,
    ram: String(deal.ram),
    ssd: String(deal.ssd),
  }});
  if (deal.cpu_cores !== null) params.set('cpu_cores', String(deal.cpu_cores));
  if (deal.gpu_cores !== null) params.set('gpu_cores', String(deal.gpu_cores));

  const response = await fetch(`/api/history?${{params.toString()}}`);
  const data = await response.json();
  chartHistoryCache.set(historyKey(deal), data);

  if (expandedChartRow !== chartRow) return;
  renderExpandedChart(chartRow, data, currentChartMode);
}}

setTimeout(() => location.reload(), 300000);
</script>
</body>
</html>"##
    );

    HttpResponse::Ok()
        .content_type("text/html; charset=utf-8")
        .body(html)
}

async fn api_prices(pool: web::Data<PgPool>) -> HttpResponse {
    let rows: Vec<PriceRow> = sqlx::query_as(
        r#"
        SELECT s.name as store, p.name as product,
               p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores,
               ph.price_chf::float8 as price_chf,
               ph.availability, ph.scraped_at::timestamp as scraped_at, pl.url
        FROM price_history ph
        JOIN product_links pl ON ph.link_id = pl.id
        JOIN products p ON pl.product_id = p.id
        JOIN stores s ON pl.store_id = s.id
        WHERE p.chip LIKE 'M4%'
        ORDER BY ph.scraped_at DESC
        LIMIT 200
        "#,
    )
    .fetch_all(pool.get_ref())
    .await
    .unwrap_or_default();

    HttpResponse::Ok().json(rows)
}

async fn api_history(pool: web::Data<PgPool>, query: web::Query<HistoryQuery>) -> HttpResponse {
    let rows: Vec<PricePoint> = sqlx::query_as(
        r#"
        SELECT s.name as store,
               ph.price_chf::float8 as price_chf,
               (pl.url LIKE 'https://www.toppreise.ch/%') as is_aggregated,
               ph.scraped_at::timestamp as scraped_at
        FROM price_history ph
        JOIN product_links pl ON ph.link_id = pl.id
        JOIN products p ON pl.product_id = p.id
        JOIN stores s ON pl.store_id = s.id
        WHERE p.chip = $1
          AND p.ram = $2
          AND p.ssd = $3
          AND (($4::int IS NULL AND p.cpu_cores IS NULL) OR p.cpu_cores = $4)
          AND (($5::int IS NULL AND p.gpu_cores IS NULL) OR p.gpu_cores = $5)
        ORDER BY ph.scraped_at ASC
        "#,
    )
    .bind(&query.chip)
    .bind(query.ram)
    .bind(query.ssd)
    .bind(query.cpu_cores)
    .bind(query.gpu_cores)
    .fetch_all(pool.get_ref())
    .await
    .unwrap_or_default();

    HttpResponse::Ok().json(rows)
}

#[derive(serde::Deserialize)]
struct HistoryQuery {
    chip: String,
    ram: i32,
    ssd: i32,
    cpu_cores: Option<i32>,
    gpu_cores: Option<i32>,
}

#[tokio::main]
async fn main() -> std::io::Result<()> {
    let database_url = std::env::var("DATABASE_URL").unwrap_or_else(|_| {
        "postgresql://tracker:change_me_in_production@db:5432/mac_tracker".into()
    });

    let dash_user = std::env::var("DASH_USER").unwrap_or_else(|_| "admin".into());
    let dash_pass = std::env::var("DASH_PASS").expect("DASH_PASS environment variable is required");

    let auth_config = web::Data::new(AuthConfig {
        username: dash_user.clone(),
        password: dash_pass,
    });

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await
        .expect("Failed to connect to database");

    println!(
        "Dashboard running on http://0.0.0.0:8080 (auth: user={})",
        dash_user
    );

    let auth_cfg = auth_config.clone();
    HttpServer::new(move || {
        let auth = HttpAuthentication::basic(basic_auth_validator);
        App::new()
            .app_data(web::Data::new(pool.clone()))
            .app_data(auth_cfg.clone())
            .wrap(auth)
            .route("/", web::get().to(index))
            .route("/api/prices", web::get().to(api_prices))
            .route("/api/history", web::get().to(api_history))
    })
    .bind("0.0.0.0:8080")?
    .run()
    .await
}

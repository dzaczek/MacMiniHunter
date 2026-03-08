use actix_web::{dev::ServiceRequest, web, App, Error, HttpResponse, HttpServer};
use actix_web_httpauth::extractors::basic::BasicAuth;
use actix_web_httpauth::middleware::HttpAuthentication;
use chrono::NaiveDateTime;
use serde::Serialize;
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;

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
        && credentials.password().map_or(false, |p| p == auth_config.password);

    if is_valid {
        Ok(req)
    } else {
        let response = HttpResponse::Unauthorized()
            .insert_header(("WWW-Authenticate", "Basic realm=\"Mac Mini Hunter\""))
            .finish();
        Err((actix_web::error::InternalError::from_response(
            "Unauthorized",
            response,
        ).into(), req))
    }
}

#[derive(Serialize, sqlx::FromRow)]
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
    scraped_at: NaiveDateTime,
    url: String,
}

#[derive(Serialize, sqlx::FromRow)]
struct BestDeal {
    product: String,
    store: String,
    price_chf: f64,
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
    scraped_at: NaiveDateTime,
}

async fn index(pool: web::Data<PgPool>) -> HttpResponse {
    let best_deals: Vec<BestDeal> = sqlx::query_as(
        r#"
        SELECT DISTINCT ON (p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores)
               p.name as product, s.name as store,
               ph.price_chf::float8 as price_chf, pl.url,
               p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores
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

    let latest: Vec<PriceRow> = sqlx::query_as(
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
          AND ph.scraped_at = (
            SELECT MAX(ph2.scraped_at) FROM price_history ph2 WHERE ph2.link_id = pl.id
        )
        ORDER BY p.chip, p.ram, p.ssd, p.cpu_cores, p.gpu_cores, ph.price_chf ASC
        "#,
    )
    .fetch_all(pool.get_ref())
    .await
    .unwrap_or_default();

    let deals_json = serde_json::to_string(&best_deals).unwrap_or_default();
    let latest_json = serde_json::to_string(&latest).unwrap_or_default();

    let html = format!(
        r##"<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mac Mini Hunter</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0a;color:#e0e0e0}}
.c{{max-width:1100px;margin:0 auto;padding:20px}}
h1{{font-size:1.8em;margin-bottom:6px;color:#fff}}
h1 span{{color:#4ade80}}
.sub{{color:#888;margin-bottom:24px;font-size:.9em}}
h2{{font-size:1.2em;margin:28px 0 12px;color:#ddd;border-bottom:1px solid #333;padding-bottom:6px}}
table{{width:100%;border-collapse:collapse;margin-bottom:16px}}
th{{background:#1a1a2e;color:#999;text-align:left;padding:10px;font-weight:500;font-size:.8em;text-transform:uppercase;letter-spacing:.5px}}
td{{padding:10px;border-bottom:1px solid #222}}
tr:hover{{background:#111}}
tr.clickable{{cursor:pointer}}
tr.clickable:hover{{background:#1a1a2e}}
tr.active{{background:#1a2a1a!important}}
.p{{font-weight:700;color:#4ade80;white-space:nowrap}}
.p.hi{{color:#f87171}}
.av{{display:inline-block;width:8px;height:8px;border-radius:50%}}
.av.y{{background:#4ade80}}.av.n{{background:#f87171}}
a{{color:#60a5fa;text-decoration:none}}a:hover{{text-decoration:underline}}
.ch{{display:inline-block;background:#2d1b69;color:#a78bfa;padding:2px 8px;border-radius:4px;font-size:.85em;font-weight:500}}
.sp{{color:#888;font-size:.85em}}
.ts{{color:#666;font-size:.8em}}
.deal{{background:#0f2a1a!important}}
.box{{background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:20px;margin-bottom:20px;display:none}}
.box.show{{display:block}}
.box h3{{color:#a78bfa;margin-bottom:12px;font-size:1.1em}}
#chart-wrap{{height:300px;position:relative}}
.loading{{color:#888;text-align:center;padding:40px}}
footer{{text-align:center;color:#555;padding:24px 0;font-size:.85em}}
</style>
</head>
<body>
<div class="c">
<h1><span>Mac Mini</span> Hunter</h1>
<p class="sub">M4 / M4 Pro &mdash; Brack &middot; Fust &middot; Apple &middot; Galaxus &middot; DQ Solutions &middot; Tutti &middot; Ricardo</p>

<h2>Best Deal per Config <span class="sp">(click row for price chart)</span></h2>
<table id="deals">
<thead><tr><th>Config</th><th>Best Store</th><th>Price</th><th>Link</th></tr></thead>
<tbody></tbody>
</table>

<div class="box" id="chart-box">
<h3 id="chart-title"></h3>
<div id="chart-wrap"><canvas id="pc"></canvas></div>
</div>

<h2>All Current Prices</h2>
<table id="prices">
<thead><tr><th></th><th>Product</th><th>Store</th><th>Price</th><th>Specs</th><th>When</th></tr></thead>
<tbody></tbody>
</table>

<footer>mminihunter &mdash; refreshes every 5 min</footer>
</div>

<script>
const deals={deals_json};
const latest={latest_json};
const fp=p=>'CHF '+p.toFixed(2);
const ta=dt=>{{const d=new Date(dt),n=new Date(),m=Math.floor((n-d)/6e4);return m<60?m+'m ago':m<1440?Math.floor(m/60)+'h ago':Math.floor(m/1440)+'d ago'}};
const ss=(c,r,s,cc,gc)=>{{
  let label=r>0?`${{c}} / ${{r}}GB / ${{s>=1000?(s/1000)+'TB':s+'GB'}}`:c;
  if(cc&&gc)label+=` (${{cc}}c/${{gc}}c)`;
  return label;
}};

// Deals table
const db=document.querySelector('#deals tbody');
deals.forEach(d=>{{
  const sp=ss(d.chip,d.ram,d.ssd,d.cpu_cores,d.gpu_cores);
  const tr=document.createElement('tr');
  tr.className='clickable deal';
  tr.dataset.chip=d.chip;tr.dataset.ram=d.ram;tr.dataset.ssd=d.ssd;
  tr.innerHTML=`<td><span class="ch">${{sp}}</span></td><td>${{d.store}}</td><td class="p">${{fp(d.price_chf)}}</td><td><a href="${{d.url}}" target="_blank" onclick="event.stopPropagation()">View&rarr;</a></td>`;
  tr.onclick=()=>loadChart(d.chip,d.ram,d.ssd,sp);
  db.appendChild(tr);
}});

// Prices table
const pb=document.querySelector('#prices tbody');
latest.forEach(r=>{{
  const cores=r.cpu_cores&&r.gpu_cores?` <span class="sp">${{r.cpu_cores}}c/${{r.gpu_cores}}c</span>`:'';
  const sp=r.ram>0?`<span class="ch">${{r.chip}}</span> <span class="sp">${{r.ram}}GB/${{r.ssd>=1000?(r.ssd/1000)+'TB':r.ssd+'GB'}}</span>${{cores}}`:'';
  pb.innerHTML+=`<tr><td><span class="av ${{r.availability?'y':'n'}}"></span></td><td><a href="${{r.url}}" target="_blank">${{r.product}}</a></td><td>${{r.store}}</td><td class="p${{r.price_chf>1500?' hi':''}}">${{fp(r.price_chf)}}</td><td>${{sp}}</td><td class="ts">${{ta(r.scraped_at)}}</td></tr>`;
}});

// Chart - loaded on click via API
let chart=null;
async function loadChart(chip,ram,ssd,label){{
  const box=document.getElementById('chart-box');
  box.className='box show';
  document.getElementById('chart-title').textContent='Price History: '+label;
  document.querySelectorAll('#deals tr').forEach(t=>t.classList.remove('active'));
  event?.target?.closest?.('tr')?.classList?.add('active');

  const wrap=document.getElementById('chart-wrap');
  wrap.innerHTML='<div class="loading">Loading...</div>';

  const res=await fetch(`/api/history?chip=${{encodeURIComponent(chip)}}&ram=${{ram}}&ssd=${{ssd}}`);
  const data=await res.json();

  wrap.innerHTML='<canvas id="pc"></canvas>';
  const ctx=document.getElementById('pc');

  const colors={{'Brack':'#60a5fa','Fust':'#f59e0b','Apple Store':'#a78bfa','Galaxus':'#4ade80','DQ Solutions':'#06b6d4','Tutti':'#fb923c','Ricardo':'#f87171'}};
  const stores=[...new Set(data.map(d=>d.store))];
  const datasets=stores.map(s=>({{
    label:s,
    data:data.filter(d=>d.store===s).map(d=>({{x:new Date(d.scraped_at),y:d.price_chf}})),
    borderColor:colors[s]||'#888',
    borderWidth:2,pointRadius:4,tension:0.3,fill:false
  }}));

  if(chart)chart.destroy();
  chart=new Chart(ctx,{{
    type:'line',
    data:{{datasets}},
    options:{{
      responsive:true,maintainAspectRatio:false,
      interaction:{{mode:'index',intersect:false}},
      plugins:{{
        legend:{{labels:{{color:'#ccc'}}}},
        tooltip:{{callbacks:{{label:c=>`${{c.dataset.label}}: CHF ${{c.parsed.y.toFixed(2)}}`}}}}
      }},
      scales:{{
        x:{{type:'time',time:{{unit:'day',tooltipFormat:'PPp'}},ticks:{{color:'#888'}},grid:{{color:'#222'}}}},
        y:{{ticks:{{color:'#888',callback:v=>'CHF '+v}},grid:{{color:'#222'}}}}
      }}
    }}
  }});
}}

setTimeout(()=>location.reload(),300000);
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
               ph.scraped_at::timestamp as scraped_at
        FROM price_history ph
        JOIN product_links pl ON ph.link_id = pl.id
        JOIN products p ON pl.product_id = p.id
        JOIN stores s ON pl.store_id = s.id
        WHERE p.chip = $1 AND p.ram = $2 AND p.ssd = $3
        ORDER BY ph.scraped_at ASC
        "#,
    )
    .bind(&query.chip)
    .bind(query.ram)
    .bind(query.ssd)
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
}

#[tokio::main]
async fn main() -> std::io::Result<()> {
    let database_url = std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "postgresql://tracker:change_me_in_production@db:5432/mac_tracker".into());

    let dash_user = std::env::var("DASH_USER")
        .unwrap_or_else(|_| "admin".into());
    let dash_pass = std::env::var("DASH_PASS")
        .expect("DASH_PASS environment variable is required");

    let auth_config = web::Data::new(AuthConfig {
        username: dash_user.clone(),
        password: dash_pass,
    });

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await
        .expect("Failed to connect to database");

    println!("Dashboard running on http://0.0.0.0:8080 (auth: user={})", dash_user);

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

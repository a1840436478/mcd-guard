"""本地网页面板：查看待确认请求、今日消费和审计记录，并用确认码确认写操作。"""

from config import WRITE_TOOL_NAMES
from confirm import get_pending
from guard import is_write_tool, tool_label, tool_rule

PANEL_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>麦麦护栏</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--text:#1f2328;--dim:#656d76;--line:#d0d7de;--accent:#da291c;--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--text:#e6edf3;--dim:#8d96a0;--line:#30363d;--accent:#ff6b5e;--ok:#3fb950;--warn:#d29922;--bad:#f85149}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 20px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
h2{font-size:16px;margin:0 0 12px}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat b{display:block;font-size:20px}.stat span{color:var(--dim);font-size:13px}
pre{background:var(--bg);border-radius:8px;padding:12px;overflow-x:auto;font:13px/1.6 ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}input{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);width:9em;letter-spacing:.2em}
button{font:inherit;padding:8px 16px;border-radius:8px;border:1px solid var(--line);cursor:pointer;background:var(--card);color:var(--text)}
button.yes{background:var(--accent);border-color:var(--accent);color:#fff}.msg{color:var(--warn);min-height:1.6em;margin-top:8px}
.empty{color:var(--dim)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:normal}.d-allowed{color:var(--ok)}.d-confirmed{color:var(--accent)}.d-blocked,.d-rejected,.d-timeout{color:var(--bad)}
.wrap{overflow-x:auto}.rules{display:flex;flex-wrap:wrap;gap:8px}.rule{border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:13px}
.r-allow{color:var(--warn)}.r-confirm{color:var(--ok)}.r-block{color:var(--bad)}
</style>
</head>
<body>
<main>
<h1>🍔 麦麦护栏</h1>
<p class="sub">AI 想动你的麦当劳账号时，先过这里。确认码只显示在护栏终端里。</p>
<section><h2>待确认</h2><div id="pending" class="empty">现在没有待确认的操作。</div></section>
<section><h2>今日概况</h2><div class="stats" id="stats"></div></section>
<section><h2>操作规则</h2><div class="rules" id="rules"></div></section>
<section><h2>今天的审计记录</h2><div class="wrap"><table><thead><tr><th>时间</th><th>工具</th><th>结论</th><th>金额</th></tr></thead><tbody id="audit"></tbody></table></div></section>
</main>
<script>
const LABEL={allowed:"放行",confirmed:"已确认",rejected:"已拒绝",timeout:"超时",blocked:"已拦截"};
const RULE={allow:"直接放行",confirm:"需确认",block:"拦截"};
const REASON={tool_rules:"按规则直接放行",readonly:"只读模式",limit:"超出消费上限",blocked_tools:"已禁用的工具",quote_failed:"核价失败"};
let shownId=null;
const yuan=f=>"¥"+(f/100).toFixed(2);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function decide(approve){
  const code=document.getElementById("code")?.value||"";
  const r=await fetch("api/decide",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:shownId,code,approve})});
  const j=await r.json();document.getElementById("msg").textContent=j.message;refresh();
}
function renderPending(p){
  const box=document.getElementById("pending");
  if(!p){shownId=null;box.className="empty";box.textContent="现在没有待确认的操作。";return}
  if(p.id!==shownId){
    shownId=p.id;box.className="";
    const card=p.card.split("\n").filter(l=>!/^\s*[=\-]+\s*$/.test(l)).join("\n").trim();
    box.innerHTML=`<pre>${esc(card)}</pre><div class="row"><input id="code" inputmode="numeric" maxlength="6" placeholder="确认码" autocomplete="off">
<button class="yes" onclick="decide(true)">确认执行</button><button onclick="decide(false)">拒绝</button><span id="left"></span></div><div class="msg" id="msg"></div>`;
  }
  document.getElementById("left").textContent=`剩 ${p.seconds_left} 秒`;
}
async function refresh(){
  try{
    const s=await (await fetch("api/state")).json();
    renderPending(s.pending);
    const p=s.policy;
    document.getElementById("stats").innerHTML=[
      ["模式",p.mode==="readonly"?"只读":"写操作需确认"],["今日已确认",`${yuan(s.spent_daily)} / ${yuan(p.max_daily_yuan*100)}`],
      ["本周已确认",`${yuan(s.spent_weekly)} / ${yuan(p.max_weekly_yuan*100)}`],["单笔上限",yuan(p.max_order_yuan*100)]
    ].map(([k,v])=>`<div class="stat"><span>${k}</span><b>${v}</b></div>`).join("");
    document.getElementById("rules").innerHTML=s.rules.map(r=>`<span class="rule">${esc(r.label)}：<b class="r-${esc(r.rule)}">${p.mode==="readonly"&&r.write&&r.rule!=="block"?"拦截（只读）":RULE[r.rule]||esc(r.rule)}</b></span>`).join("");
    document.getElementById("audit").innerHTML=s.recent.length?s.recent.map(r=>`<tr><td>${esc(r.time.slice(11))}</td><td>${esc(r.tool)}</td>
<td class="d-${esc(r.decision)}">${LABEL[r.decision]||esc(r.decision)}${r.reason?"（"+esc(REASON[r.reason]||r.reason)+"）":""}</td><td>${r.price_fen!=null?yuan(r.price_fen):""}</td></tr>`).join(""):'<tr><td colspan="4" class="empty">今天还没有调用。</td></tr>';
  }catch(e){}
}
refresh();setInterval(refresh,1500);
</script>
</body>
</html>
"""


def build_panel_state(state):
    """
    组装网页面板需要的数据。

    :param state: 服务状态，需含 policy、ctx.spent、recent
    :return: dict
    """
    daily, weekly = state["ctx"]["spent"]()
    recent = list(reversed(state["recent"]()))
    return {
        "pending": get_pending(),
        "policy": state["policy"],
        "spent_daily": daily,
        "spent_weekly": weekly,
        "rules": [{"tool": n, "label": tool_label(n), "rule": tool_rule(n, state["policy"]), "write": is_write_tool(n)}
                  for n in [*WRITE_TOOL_NAMES, *sorted(set(state["policy"]["tool_rules"]) - set(WRITE_TOOL_NAMES))]],
        "recent": [{k: r.get(k) for k in ("time", "tool", "decision", "reason", "price_fen")} for r in recent],
    }

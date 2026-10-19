// claim-page — the small portal page a person opens in their browser:
// sign up / sign in (Supabase's own email auth), then type the code shown
// on the install's screen. Served straight from an edge function so no
// separate website hosting is needed yet; later the real portal domain can
// serve this same HTML.
//
// Deploy with "Verify JWT" OFF for THIS function only — a browser visits it
// with no headers. The page itself holds only the PUBLIC anon key (safe by
// design); every privileged step happens in device-claim, which verifies the
// person's session server-side.
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

const HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NeuralOps — claim your server</title>
<style>
  :root { --bg:#0e1116; --card:#171c24; --text:#e8ecf1; --dim:#93a0b4;
          --accent:#4f8cff; --ok:#3ecf8e; --err:#ff6b6b; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:16px/1.5 system-ui, sans-serif; display:grid;
         place-items:center; min-height:100vh; padding:16px; box-sizing:border-box; }
  .card { background:var(--card); border-radius:14px; padding:32px;
          width:100%; max-width:420px; box-shadow:0 8px 40px rgb(0 0 0 / .4); }
  h1 { font-size:22px; margin:0 0 4px; }
  p.sub { color:var(--dim); margin:0 0 24px; font-size:14px; }
  label { display:block; font-size:13px; color:var(--dim); margin:14px 0 4px; }
  input { width:100%; box-sizing:border-box; padding:11px 12px; border-radius:8px;
          border:1px solid #2a3240; background:#0f141b; color:var(--text);
          font-size:16px; }
  input:focus { outline:2px solid var(--accent); border-color:transparent; }
  button { width:100%; margin-top:18px; padding:12px; border:0; border-radius:8px;
           background:var(--accent); color:#fff; font-size:16px; font-weight:600;
           cursor:pointer; }
  button.secondary { background:transparent; color:var(--dim); margin-top:8px; }
  .msg { margin-top:14px; font-size:14px; min-height:20px; }
  .msg.ok { color:var(--ok); } .msg.err { color:var(--err); }
  .code-input { letter-spacing:6px; text-align:center; font-size:24px; }
  .who { font-size:13px; color:var(--dim); margin-bottom:16px; }
  .who a { color:var(--dim); }
  .hide { display:none; }
</style>
</head>
<body>
<div class="card">
  <!-- Step 1: sign in / sign up -->
  <div id="auth">
    <h1>NeuralOps</h1>
    <p class="sub">Sign in to claim your new server.</p>
    <label>Email</label>
    <input id="email" type="email" autocomplete="email" placeholder="you@company.com">
    <label>Password</label>
    <input id="password" type="password" autocomplete="current-password" placeholder="••••••••">
    <button id="signin">Sign in</button>
    <button id="signup" class="secondary">New here? Create an account</button>
    <div id="authmsg" class="msg"></div>
  </div>

  <!-- Step 2: the code -->
  <div id="claim" class="hide">
    <h1>Enter your code</h1>
    <p class="sub">It is showing on your server's setup screen right now.</p>
    <div class="who">Signed in as <b id="whoami"></b> · <a href="#" id="signout">sign out</a></div>
    <input id="code" class="code-input" inputmode="numeric" maxlength="7" placeholder="000-000">
    <button id="do-claim">Claim this server</button>
    <div id="claimmsg" class="msg"></div>
  </div>
</div>

<script type="module">
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";
const supabase = createClient("${SUPABASE_URL}", "${ANON_KEY}");
const $ = (id) => document.getElementById(id);

function show(section) {
  $("auth").classList.toggle("hide", section !== "auth");
  $("claim").classList.toggle("hide", section !== "claim");
}
async function refresh() {
  const { data } = await supabase.auth.getSession();
  if (data.session) { $("whoami").textContent = data.session.user.email; show("claim"); }
  else { show("auth"); }
}
$("signin").onclick = async () => {
  $("authmsg").className = "msg"; $("authmsg").textContent = "Signing in…";
  const { error } = await supabase.auth.signInWithPassword(
    { email: $("email").value.trim(), password: $("password").value });
  if (error) { $("authmsg").className = "msg err"; $("authmsg").textContent = error.message; }
  else refresh();
};
$("signup").onclick = async () => {
  $("authmsg").className = "msg"; $("authmsg").textContent = "Creating your account…";
  const { data, error } = await supabase.auth.signUp(
    { email: $("email").value.trim(), password: $("password").value });
  if (error) { $("authmsg").className = "msg err"; $("authmsg").textContent = error.message; return; }
  if (data.session) refresh();
  else { $("authmsg").className = "msg ok";
         $("authmsg").textContent = "Check your email to confirm, then sign in here."; }
};
$("signout").onclick = async (e) => { e.preventDefault(); await supabase.auth.signOut(); show("auth"); };
$("code").oninput = () => {  // auto-format 483291 → 483-291
  const d = $("code").value.replace(/[^0-9]/g, "").slice(0, 6);
  $("code").value = d.length > 3 ? d.slice(0,3) + "-" + d.slice(3) : d;
};
$("do-claim").onclick = async () => {
  $("claimmsg").className = "msg"; $("claimmsg").textContent = "Claiming…";
  const { data } = await supabase.auth.getSession();
  if (!data.session) { show("auth"); return; }
  const resp = await fetch("${SUPABASE_URL}/functions/v1/device-claim", {
    method: "POST",
    headers: { "Content-Type": "application/json",
               "apikey": "${ANON_KEY}",
               "Authorization": "Bearer " + data.session.access_token },
    body: JSON.stringify({ code: $("code").value }),
  });
  const result = await resp.json().catch(() => ({}));
  if (resp.ok && result.ok) {
    $("claimmsg").className = "msg ok";
    $("claimmsg").textContent = "Done! Go back to your server — it is finishing setup with you as the owner.";
  } else {
    $("claimmsg").className = "msg err";
    $("claimmsg").textContent = result.error || "Could not claim — try again.";
  }
};
refresh();
</script>
</body>
</html>`;

Deno.serve(() =>
  new Response(HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } }));

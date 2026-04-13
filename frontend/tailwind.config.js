/** @type {import('tailwindcss').Config} */
// #region agent log
fetch('http://127.0.0.1:7661/ingest/23552c26-aa5a-4956-8d58-0ca24af11a9c',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'6378ff'},body:JSON.stringify({sessionId:'6378ff',runId:'pre-fix',hypothesisId:'C',location:'frontend/tailwind.config.js:module',message:'tailwind config loaded',data:{content:['./app/**/*.{js,ts,jsx,tsx,mdx}','!./app/caiwuyo/**','./components/**/*.{js,ts,jsx,tsx,mdx}']},timestamp:Date.now()})}).catch(()=>{});
// #endregion
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "!./app/caiwuyo/**",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

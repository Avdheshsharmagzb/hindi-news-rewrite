import { useEffect, useState } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Newspaper, Loader2, ArrowLeft, Calendar } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const MEDIA = (p) => (p ? `${process.env.REACT_APP_BACKEND_URL}${p}` : null);
const BRAND = "गाजियाबाद टाइम्स";

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("hi-IN", { day: "numeric", month: "long", year: "numeric" });
  } catch {
    return "";
  }
}

export default function PublicNews() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.documentElement.classList.remove("dark");
    axios
      .get(`${API}/public/news`)
      .then((r) => setItems(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const lead = items[0];
  const rest = items.slice(1);

  return (
    <div className="min-h-screen bg-[#faf8f4] text-slate-900">
      {/* Masthead */}
      <header className="border-b-4 border-double border-primary">
        <div className="max-w-6xl mx-auto px-6 py-6 flex flex-col items-center text-center">
          <div className="flex items-center gap-3">
            <div className="h-11 w-11 rounded-lg bg-primary flex items-center justify-center">
              <Newspaper className="h-6 w-6 text-white" />
            </div>
            <h1 className="font-hindi font-bold text-4xl sm:text-5xl tracking-tight text-primary" data-testid="public-masthead">
              {BRAND}
            </h1>
          </div>
          <p className="font-hindi text-sm text-slate-500 mt-2 tracking-widest">विश्वसनीय • निष्पक्ष • सटीक समाचार</p>
          <div className="w-full flex items-center justify-between border-t border-b border-slate-300 mt-4 py-1.5 text-xs font-mono uppercase tracking-wider text-slate-500">
            <span>{new Date().toLocaleDateString("hi-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</span>
            <a href="/" className="inline-flex items-center gap-1 hover:text-primary" data-testid="back-to-admin">
              <ArrowLeft className="h-3.5 w-3.5" /> एडमिन डैशबोर्ड
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {loading ? (
          <div className="flex items-center justify-center py-28 text-slate-500 gap-2">
            <Loader2 className="h-5 w-5 animate-spin" /> समाचार लोड हो रहे हैं...
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-28 text-slate-500 font-hindi">
            अभी कोई प्रकाशित समाचार नहीं। एडमिन डैशबोर्ड से खबरें प्रकाशित करें।
          </div>
        ) : (
          <>
            {/* Lead story */}
            {lead && (
              <motion.article
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="grid md:grid-cols-2 gap-6 mb-10 pb-10 border-b border-slate-300"
                data-testid={`public-lead-${lead.id}`}
              >
                {lead.image_url && (
                  <div className="rounded-xl overflow-hidden shadow-lg">
                    <img src={MEDIA(lead.image_url)} alt={BRAND} className="w-full h-72 md:h-full object-cover" />
                  </div>
                )}
                <div className={lead.image_url ? "" : "md:col-span-2"}>
                  <span className="inline-block text-xs font-bold uppercase tracking-wider text-primary mb-3 font-hindi">
                    {lead.category}
                  </span>
                  <h2 className="font-hindi font-bold text-3xl leading-snug mb-3">{lead.headline}</h2>
                  <p className="font-hindi text-slate-700 leading-relaxed text-lg">{lead.content}</p>
                  <div className="flex items-center gap-2 mt-4 text-xs text-slate-500 font-mono">
                    <Calendar className="h-3.5 w-3.5" /> {formatDate(lead.published_at)}
                    <span className="opacity-40">•</span>
                    <span className="text-primary font-semibold font-hindi">{lead.publisher_brand}</span>
                  </div>
                </div>
              </motion.article>
            )}

            {/* Grid of remaining */}
            <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
              {rest.map((it, i) => (
                <motion.article
                  key={it.id}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05, duration: 0.35 }}
                  className="flex flex-col"
                  data-testid={`public-article-${it.id}`}
                >
                  {it.image_url && (
                    <div className="rounded-lg overflow-hidden mb-3 shadow">
                      <img src={MEDIA(it.image_url)} alt={BRAND} className="w-full h-48 object-cover" loading="lazy" />
                    </div>
                  )}
                  <span className="text-[11px] font-bold uppercase tracking-wider text-primary mb-1.5 font-hindi">
                    {it.category}
                  </span>
                  <h3 className="font-hindi font-bold text-xl leading-snug mb-2">{it.headline}</h3>
                  <p className="font-hindi text-slate-600 leading-relaxed text-sm line-clamp-4 flex-1">{it.content}</p>
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-200 text-xs text-slate-500 font-mono">
                    <Calendar className="h-3.5 w-3.5" /> {formatDate(it.published_at)}
                    <span className="opacity-40">•</span>
                    <span className="text-primary font-semibold font-hindi">{it.publisher_brand}</span>
                  </div>
                </motion.article>
              ))}
            </div>
          </>
        )}
      </main>

      <footer className="border-t border-slate-300 mt-10 py-6 text-center text-xs text-slate-500 font-hindi">
        © {new Date().getFullYear()} {BRAND} — सर्वाधिकार सुरक्षित
      </footer>
    </div>
  );
}

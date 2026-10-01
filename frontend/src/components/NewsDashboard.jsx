import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  Newspaper, Sparkles, Loader2, Sun, Moon, Plus, Send, Trash2,
  GitCompareArrows, ShieldCheck, Search, FileText, Clock, DownloadCloud, ImagePlus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { NEWS } from "@/constants/testIds";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const MEDIA = (p) => (p ? `${process.env.REACT_APP_BACKEND_URL}${p}` : null);
const BRAND = "गाजियाबाद टाइम्स";

const STATUSES = ["All", "Pending_Review", "Rewritten_Pending_Publish", "Published"];
const CATEGORIES = ["National", "Politics", "Business", "Technology", "Sports"];

const STATUS_META = {
  Pending_Review: {
    label: "समीक्षा हेतु लंबित",
    en: "Pending Review",
    cls: "bg-amber-500/10 text-amber-500 border-amber-500/25",
  },
  Rewritten_Pending_Publish: {
    label: "प्रकाशन हेतु लंबित",
    en: "Rewritten",
    cls: "bg-indigo-500/10 text-indigo-400 border-indigo-500/25",
  },
  Published: {
    label: "प्रकाशित",
    en: "Published",
    cls: "bg-emerald-500/10 text-emerald-500 border-emerald-500/25",
  },
};

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: (i) => ({ opacity: 1, y: 0, transition: { delay: i * 0.04, duration: 0.35 } }),
};

export default function NewsDashboard() {
  const [dark, setDark] = useState(true);
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({ total: 0, pending: 0, rewritten: 0, published: 0 });
  const [filter, setFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [rewritingId, setRewritingId] = useState(null);
  const [compareItem, setCompareItem] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [region, setRegion] = useState("All");
  const [genImageId, setGenImageId] = useState(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const loadAll = async () => {
    try {
      const [news, st] = await Promise.all([
        axios.get(`${API}/news`),
        axios.get(`${API}/stats`),
      ]);
      setItems(news.data);
      setStats(st.data);
    } catch (e) {
      toast.error("समाचार लोड करने में विफल");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const filtered = useMemo(() => {
    return items.filter((it) => {
      const okStatus = filter === "All" || it.status === filter;
      const okRegion = region === "All" || it.category === region;
      const q = search.trim().toLowerCase();
      const okSearch =
        !q ||
        (it.headline || "").toLowerCase().includes(q) ||
        (it.content || "").toLowerCase().includes(q) ||
        (it.rewritten_headline || "").toLowerCase().includes(q);
      return okStatus && okRegion && okSearch;
    });
  }, [items, filter, region, search]);

  const regions = useMemo(
    () => ["All", ...Array.from(new Set(items.map((i) => i.category)))],
    [items]
  );

  const handleFetch = async () => {
    setFetching(true);
    toast.loading("ताज़ा खबरें फेच हो रही हैं (अधिकतम 4 घंटे पुरानी)...", { id: "fetch" });
    try {
      const { data } = await axios.post(`${API}/news/fetch`);
      const n = data.fetched || 0;
      toast.success(
        n > 0 ? `${n} नई खबरें जोड़ी गईं (Pending Review)` : "कोई नई खबर नहीं — सभी पहले से मौजूद",
        { id: "fetch" }
      );
      await loadAll();
    } catch (e) {
      toast.error("न्यूज़ फेच विफल", { id: "fetch" });
    } finally {
      setFetching(false);
    }
  };

  const handleRewrite = async (id) => {
    setRewritingId(id);
    toast.loading("उच्च पत्रकारिता श्रेणी में रूपांतरण जारी...", { id: `rw-${id}` });
    try {
      const { data } = await axios.post(`${API}/news/${id}/rewrite`);
      toast.success("पुनर्लेखन सफल — प्रकाशन हेतु तैयार", { id: `rw-${id}` });
      setItems((prev) => prev.map((it) => (it.id === id ? data : it)));
      await refreshStats();
      setCompareItem(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "AI पुनर्लेखन विफल", { id: `rw-${id}` });
    } finally {
      setRewritingId(null);
    }
  };

  const handlePublish = async (id) => {
    try {
      const { data } = await axios.post(`${API}/news/${id}/publish`);
      toast.success("समाचार प्रकाशित किया गया");
      setItems((prev) => prev.map((it) => (it.id === id ? data : it)));
      await refreshStats();
      setCompareItem(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "प्रकाशन विफल");
    }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`${API}/news/${id}`);
      setItems((prev) => prev.filter((it) => it.id !== id));
      await refreshStats();
      toast.success("आइटम हटाया गया");
    } catch (e) {
      toast.error("हटाने में विफल");
    }
  };

  const handleGenerateImage = async (id) => {
    setGenImageId(id);
    toast.loading("गाजियाबाद टाइम्स फोटो तैयार हो रही है...", { id: `img-${id}` });
    try {
      const { data } = await axios.post(`${API}/news/${id}/generate-image`);
      toast.success("वाटरमार्क सहित फोटो तैयार", { id: `img-${id}` });
      setItems((prev) => prev.map((it) => (it.id === id ? data : it)));
      setCompareItem((ci) => (ci && ci.id === id ? data : ci));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "फोटो जेनरेशन विफल", { id: `img-${id}` });
    } finally {
      setGenImageId(null);
    }
  };

  const refreshStats = async () => {
    const { data } = await axios.get(`${API}/stats`);
    setStats(data);
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div
        className="border-b border-border relative overflow-hidden"
        style={{
          backgroundImage:
            "linear-gradient(to right, hsl(var(--card)) 0%, hsl(var(--card)/0.6) 100%)",
        }}
        data-testid={NEWS.dashboard}
      >
        <div
          className="absolute inset-0 opacity-[0.04] pointer-events-none"
          style={{
            backgroundImage:
              "url(https://images.unsplash.com/photo-1566378246598-5b11a0d486cc?crop=entropy&cs=srgb&fm=jpg&q=85&w=1400)",
            backgroundSize: "cover",
          }}
        />
        <header className="max-w-7xl mx-auto px-6 py-7 flex items-center justify-between relative">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/30">
              <Newspaper className="h-6 w-6 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-2xl md:text-3xl font-hindi font-bold leading-tight tracking-wide">
                संपादकीय न्यूज़रूम
              </h1>
              <p className="text-xs font-mono uppercase tracking-[0.25em] text-muted-foreground mt-1">
                AI Hindi Rewrite CMS
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setDark((d) => !d)}
            data-testid={NEWS.themeToggleBtn}
            className="rounded-full"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </header>

        <div className="max-w-7xl mx-auto px-6 pb-7 grid grid-cols-2 md:grid-cols-4 gap-3 relative">
          <StatCard tid={NEWS.statTotal} label="कुल समाचार" value={stats.total} icon={FileText} tone="text-foreground" />
          <StatCard tid={NEWS.statPending} label="समीक्षा लंबित" value={stats.pending} icon={Clock} tone="text-amber-500" />
          <StatCard tid={NEWS.statRewritten} label="पुनर्लिखित" value={stats.rewritten} icon={Sparkles} tone="text-indigo-400" />
          <StatCard tid={NEWS.statPublished} label="प्रकाशित" value={stats.published} icon={ShieldCheck} tone="text-emerald-500" />
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex flex-col md:flex-row md:items-center gap-3 mb-6">
          <div className="flex flex-wrap gap-2 flex-1">
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                data-testid={NEWS.statusFilter(s)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-colors border ${
                  filter === s
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-transparent border-border text-muted-foreground hover:text-foreground hover:border-foreground/30"
                }`}
              >
                {s === "All" ? "सभी" : STATUS_META[s].label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="खोजें..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 w-full md:w-48"
                data-testid="news-search-input"
              />
            </div>
            <Select value={region} onValueChange={setRegion}>
              <SelectTrigger className="w-44" data-testid={NEWS.regionFilter}>
                <SelectValue placeholder="श्रेणी" />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                {regions.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r === "All" ? "सभी श्रेणियाँ" : r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              onClick={handleFetch}
              disabled={fetching}
              variant="outline"
              data-testid={NEWS.fetchNewsBtn}
              className="gap-2 whitespace-nowrap"
            >
              {fetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <DownloadCloud className="h-4 w-4" />}
              न्यूज़ फेच करें
            </Button>
            <Button onClick={() => setAddOpen(true)} data-testid={NEWS.addNewsBtn} className="gap-2 whitespace-nowrap">
              <Plus className="h-4 w-4" /> नया समाचार
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24 text-muted-foreground gap-2">
            <Loader2 className="h-5 w-5 animate-spin" /> लोड हो रहा है...
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-24 text-muted-foreground">कोई समाचार नहीं मिला।</div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <AnimatePresence>
              {filtered.map((it, i) => (
                <motion.div
                  key={it.id}
                  custom={i}
                  variants={fadeUp}
                  initial="hidden"
                  animate="show"
                  layout
                  data-testid={NEWS.newsCard(it.id)}
                  className="rounded-xl border border-border bg-card p-5 flex flex-col hover:border-primary/40 transition-colors"
                >
                  <div className="flex items-center justify-between mb-3">
                    <Badge variant="outline" className="font-mono text-[10px] uppercase tracking-wider">
                      {it.category}
                    </Badge>
                    <span className={`text-[11px] px-2.5 py-1 rounded-full border font-medium ${STATUS_META[it.status].cls}`}>
                      {STATUS_META[it.status].label}
                    </span>
                  </div>

                  {it.status !== "Pending_Review" && it.image_url && (
                    <div className="mb-3 rounded-lg overflow-hidden border border-border">
                      <img
                        src={MEDIA(it.image_url)}
                        alt={BRAND}
                        data-testid={NEWS.newsImage(it.id)}
                        className="w-full h-44 object-cover"
                        loading="lazy"
                      />
                    </div>
                  )}

                  <h3 className={`text-lg font-semibold leading-snug mb-2 ${it.status === "Pending_Review" ? "" : "font-hindi"}`}>
                    {it.status === "Pending_Review" ? it.headline : it.rewritten_headline}
                  </h3>
                  <p className={`text-sm text-muted-foreground line-clamp-3 flex-1 ${it.status === "Pending_Review" ? "" : "font-hindi"}`}>
                    {it.status === "Pending_Review" ? it.content : it.rewritten_content}
                  </p>

                  <div className="flex items-center gap-2 mt-3 text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
                    {it.status === "Pending_Review" ? (
                      <>
                        <span>स्रोत: {it.source || "—"}</span>
                        <span className="opacity-40">•</span>
                        <span>{it.source_language === "hi" ? "हिंदी" : "English"}</span>
                      </>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-primary font-semibold font-hindi normal-case tracking-normal text-xs">
                        <ShieldCheck className="h-3.5 w-3.5" /> {BRAND}
                      </span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t border-border">
                    {it.status === "Pending_Review" && (
                      <>
                        <Button
                          size="sm"
                          onClick={() => handleRewrite(it.id)}
                          disabled={rewritingId === it.id}
                          data-testid={NEWS.approveRewriteBtn(it.id)}
                          className="gap-2"
                        >
                          {rewritingId === it.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Sparkles className="h-4 w-4" />
                          )}
                          Approve for Rewrite
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleDelete(it.id)} data-testid={NEWS.deleteBtn(it.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                    {it.status === "Rewritten_Pending_Publish" && (
                      <>
                        <Button size="sm" variant="outline" onClick={() => setCompareItem(it)} data-testid={NEWS.compareBtn(it.id)} className="gap-2">
                          <GitCompareArrows className="h-4 w-4" /> तुलना देखें
                        </Button>
                        {!it.image_url && (
                          <Button size="sm" variant="secondary" onClick={() => handleGenerateImage(it.id)} disabled={genImageId === it.id} data-testid={NEWS.imageGenBtn(it.id)} className="gap-2">
                            {genImageId === it.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />} फोटो जेनरेट करें
                          </Button>
                        )}
                        <Button size="sm" onClick={() => handlePublish(it.id)} data-testid={NEWS.publishBtn(it.id)} className="gap-2">
                          <Send className="h-4 w-4" /> प्रकाशित करें
                        </Button>
                      </>
                    )}
                    {it.status === "Published" && (
                      <>
                        <Button size="sm" variant="outline" onClick={() => setCompareItem(it)} data-testid={NEWS.compareBtn(it.id)} className="gap-2">
                          <GitCompareArrows className="h-4 w-4" /> लेख देखें
                        </Button>
                        {!it.image_url && (
                          <Button size="sm" variant="secondary" onClick={() => handleGenerateImage(it.id)} disabled={genImageId === it.id} data-testid={NEWS.imageGenBtn(it.id)} className="gap-2">
                            {genImageId === it.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />} फोटो जेनरेट करें
                          </Button>
                        )}
                      </>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </main>

      <ComparisonModal
        item={compareItem}
        onClose={() => setCompareItem(null)}
        onPublish={handlePublish}
        onGenerateImage={handleGenerateImage}
        generatingId={genImageId}
      />
      <AddNewsModal open={addOpen} onClose={() => setAddOpen(false)} onCreated={loadAll} />
    </div>
  );
}

function StatCard({ tid, label, value, icon: Icon, tone }) {
  return (
    <div data-testid={tid} className="rounded-xl border border-border bg-card/60 backdrop-blur px-4 py-3 flex items-center gap-3">
      <Icon className={`h-5 w-5 ${tone}`} />
      <div>
        <div className={`text-2xl font-bold leading-none ${tone}`}>{value}</div>
        <div className="text-xs text-muted-foreground mt-1 font-hindi">{label}</div>
      </div>
    </div>
  );
}

function ComparisonModal({ item, onClose, onPublish, onGenerateImage, generatingId }) {
  if (!item) return null;
  return (
    <Dialog open={!!item} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl max-h-[88vh] overflow-y-auto" data-testid={NEWS.comparisonModal}>
        <DialogHeader>
          <DialogTitle className="text-xl font-display flex items-center gap-2">
            <GitCompareArrows className="h-5 w-5 text-primary" /> मूल बनाम पुनर्लिखित
          </DialogTitle>
          <DialogDescription className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-emerald-500 text-xs font-medium">
              <ShieldCheck className="h-4 w-4" /> 100% तथ्य सुरक्षित • शून्य मात्रा/वर्तनी त्रुटि • स्रोत पूर्णतः हटाया गया
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="grid md:grid-cols-2 gap-4 mt-2">
          <div className="rounded-lg border border-border bg-secondary/40 p-4">
            <div className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground mb-3">
              मूल (Original)
            </div>
            <h4 className="font-semibold mb-2" data-testid={NEWS.originalHeadline}>{item.headline}</h4>
            <p className="text-sm text-muted-foreground leading-relaxed" data-testid={NEWS.originalContent}>
              {item.content}
            </p>
          </div>
          <div className="rounded-lg border border-primary/30 bg-primary/[0.04] p-4">
            <div className="text-[11px] font-mono uppercase tracking-wider text-primary mb-3">
              पुनर्लिखित (उच्च पत्रकारिता श्रेणी)
            </div>

            {item.image_url ? (
              <div className="mb-3 rounded-lg overflow-hidden border border-primary/30">
                <img src={MEDIA(item.image_url)} alt={BRAND} data-testid="comparison-image" className="w-full h-56 object-cover" />
              </div>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onGenerateImage(item.id)}
                disabled={generatingId === item.id}
                data-testid={`generate-image-btn-${item.id}-modal`}
                className="gap-2 mb-3"
              >
                {generatingId === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
                गाजियाबाद टाइम्स फोटो जेनरेट करें
              </Button>
            )}

            <div className="text-[11px] font-semibold text-primary mb-2 flex items-center gap-1 font-hindi">
              <ShieldCheck className="h-3.5 w-3.5" /> {BRAND}
            </div>
            <h4 className="font-semibold mb-2 font-hindi" data-testid={NEWS.rewrittenHeadline}>
              {item.rewritten_headline}
            </h4>
            <p className="text-sm leading-relaxed font-hindi" data-testid={NEWS.rewrittenContent}>
              {item.rewritten_content}
            </p>
          </div>
        </div>

        {item.status === "Rewritten_Pending_Publish" && (
          <DialogFooter className="mt-4">
            <Button onClick={() => onPublish(item.id)} data-testid={NEWS.modalPublishBtn} className="gap-2">
              <Send className="h-4 w-4" /> अभी प्रकाशित करें
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function AddNewsModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState({
    headline: "", content: "", category: "National", source: "", source_language: "en",
  });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!form.headline.trim() || !form.content.trim()) {
      toast.error("शीर्षक और सामग्री आवश्यक हैं");
      return;
    }
    setSaving(true);
    try {
      await axios.post(`${API}/news`, form);
      toast.success("समाचार जोड़ा गया (Pending Review)");
      setForm({ headline: "", content: "", category: "National", source: "", source_language: "en" });
      onClose();
      onCreated();
    } catch (e) {
      toast.error("जोड़ने में विफल");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl" data-testid={NEWS.addModal}>
        <DialogHeader>
          <DialogTitle className="font-display text-xl">नया समाचार जोड़ें</DialogTitle>
          <DialogDescription>कच्चा समाचार दर्ज करें — यह Pending Review में जाएगा।</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label>शीर्षक</Label>
            <Input value={form.headline} onChange={(e) => setForm({ ...form, headline: e.target.value })} data-testid={NEWS.addHeadlineInput} />
          </div>
          <div className="space-y-1.5">
            <Label>सामग्री</Label>
            <Textarea rows={6} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} data-testid={NEWS.addContentInput} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label>श्रेणी</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger data-testid="add-category-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>भाषा</Label>
              <Select value={form.source_language} onValueChange={(v) => setForm({ ...form, source_language: v })}>
                <SelectTrigger data-testid="add-language-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="hi">हिंदी</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>स्रोत</Label>
              <Input value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} data-testid="add-source-input" />
            </div>
          </div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose}>रद्द करें</Button>
          <Button onClick={submit} disabled={saving} data-testid={NEWS.addSubmitBtn} className="gap-2">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} जोड़ें
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

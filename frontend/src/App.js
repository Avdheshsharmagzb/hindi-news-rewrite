import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import NewsDashboard from "@/components/NewsDashboard";
import PublicNews from "@/components/PublicNews";

function App() {
  return (
    <div className="App">
      <Toaster position="top-right" richColors closeButton />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<NewsDashboard />} />
          <Route path="/news" element={<PublicNews />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;

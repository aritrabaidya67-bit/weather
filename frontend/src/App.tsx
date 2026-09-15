/** Router + page transitions. */

import { AnimatePresence, motion } from "framer-motion";
import { Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { Card, EmptyState } from "./components/common/Ui";
import AlertsPage from "./pages/AlertsPage";
import Analytics from "./pages/Analytics";
import ChatPage from "./pages/ChatPage";
import Dashboard from "./pages/Dashboard";
import DevicePage from "./pages/DevicePage";
import PredictionsPage from "./pages/PredictionsPage";
import RiskPage from "./pages/RiskPage";
import SensorDetail from "./pages/SensorDetail";
import Sensors from "./pages/Sensors";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  const location = useLocation();
  return (
    <AppShell>
      <AnimatePresence mode="wait">
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.22, ease: "easeOut" }}
        >
          <Routes location={location}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/sensors" element={<Sensors />} />
            <Route path="/sensors/:channelId" element={<SensorDetail />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/risk" element={<RiskPage />} />
            <Route path="/predictions" element={<PredictionsPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/device" element={<DevicePage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route
              path="*"
              element={
                <Card>
                  <EmptyState
                    title="Page not found"
                    message="That route does not exist. Use the navigation to reach the dashboard, sensors, analytics, risk, forecast, alerts, hardware or the AI analyst."
                  />
                </Card>
              }
            />
          </Routes>
        </motion.div>
      </AnimatePresence>
    </AppShell>
  );
}

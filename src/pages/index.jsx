import Layout from "./Layout.jsx";

import Dashboard from "./Dashboard";

import Expediting from "./Expediting";

import Upload from "./Upload";

import Inspectors from "./Inspectors";

import TPIAgencies from "./TPIAgencies";

import Profile from "./Profile";

import UserManagement from "./UserManagement";

import Reports from "./Reports";

import TPIPerformance from "./TPIPerformance";

import Signup from "./Signup";

import Login from "./Login";

import VendorPortal from "./VendorPortal";

import { BrowserRouter as Router, Route, Routes, useLocation, Navigate } from 'react-router-dom';

const PAGES = {

    Dashboard: Dashboard,

    Inspection: Dashboard,

    Expediting: Expediting,

    VendorPortal: VendorPortal,

    Upload: Upload,

    Inspectors: Inspectors,

    TPIAgencies: TPIAgencies,

    Profile: Profile,

    UserManagement: UserManagement,

    Reports: Reports,

    TPIPerformance: TPIPerformance,

}

function HomeLanding() {
    try {
        const raw = typeof window !== 'undefined' ? localStorage.getItem('inspectflow_mock_session') : null;
        const user = raw ? JSON.parse(raw) : null;
        const role = user?.inspection_role || user?.role;
        if (role === 'vendor') return <Navigate to="/Expediting?sec=portal" replace />;
        if (role === 'field_expeditor') return <Navigate to="/Expediting?sec=field" replace />;
        if (['expediting_manager', 'expeditor', 'doc_expeditor'].includes(role)) {
            return <Navigate to="/Expediting?sec=dash" replace />;
        }
        const activeDept = typeof window !== 'undefined' ? localStorage.getItem('inspectflow_active_dept') : null;
        if (activeDept === 'expediting') {
            return <Navigate to="/Expediting?sec=dash" replace />;
        }
    } catch {}
    return <Dashboard />;
}

function _getCurrentPage(url) {
    if (url.endsWith('/')) {
        url = url.slice(0, -1);
    }
    let urlLastPart = url.split('/').pop();
    if (urlLastPart.includes('?')) {
        urlLastPart = urlLastPart.split('?')[0];
    }

    const pageName = Object.keys(PAGES).find(page => page.toLowerCase() === urlLastPart.toLowerCase());
    return pageName || Object.keys(PAGES)[0];
}

// Create a wrapper component that uses useLocation inside the Router context
function PagesContent() {
    const location = useLocation();
    const currentPage = _getCurrentPage(location.pathname);

    return (
        <Routes>
            <Route path="/signup" element={<Signup />} />
            <Route path="/login" element={<Login />} />
            <Route path="*" element={
                <Layout currentPageName={currentPage}>
                    <Routes>
                        <Route path="/" element={<HomeLanding />} />
                        <Route path="/Dashboard" element={<Dashboard />} />
                        <Route path="/Inspection" element={<Dashboard />} />
                        <Route path="/Expediting" element={<Expediting />} />
                        <Route path="/VendorPortal" element={<VendorPortal />} />
                        <Route path="/vendor-portal" element={<VendorPortal />} />
                        <Route path="/Upload" element={<Upload />} />
                        <Route path="/Inspectors" element={<Inspectors />} />
                        <Route path="/TPIAgencies" element={<TPIAgencies />} />
                        <Route path="/Profile" element={<Profile />} />
                        <Route path="/UserManagement" element={<UserManagement />} />
                        <Route path="/Reports" element={<Reports />} />
                        <Route path="/TPIPerformance" element={<TPIPerformance />} />
                        <Route path="*" element={<HomeLanding />} />
                    </Routes>
                </Layout>
            } />
        </Routes>
    );
}

export default function Pages() {
    return (
        <Router>
            <PagesContent />
        </Router>
    );
}
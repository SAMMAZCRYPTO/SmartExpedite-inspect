import React, { useEffect, useState } from 'react';
import { auth } from '@/api/entities';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FileText, ShieldCheck } from 'lucide-react';

export default function Login() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [devAccounts, setDevAccounts] = useState([]);
    const [authMode, setAuthMode] = useState('production');

    useEffect(() => {
        const loadDevMode = async () => {
            const res = await auth.getDevAccounts();
            setAuthMode(res?.auth_mode || 'production');
            setDevAccounts(res?.accounts || []);
        };
        loadDevMode();
    }, []);

    const redirectAfterSignIn = (currentUser) => {
        const role = currentUser?.inspection_role || currentUser?.role;
        const isExpediting = ['expediting_manager', 'expeditor', 'doc_expeditor', 'field_expeditor', 'vendor'].includes(role);

        if (isExpediting) {
            localStorage.setItem('inspectflow_active_dept', 'expediting');
            if (role === 'vendor') {
                window.location.href = '/Expediting?sec=portal';
            } else if (role === 'field_expeditor') {
                window.location.href = '/Expediting?sec=field';
            } else {
                window.location.href = '/Expediting?sec=dash';
            }
        } else {
            localStorage.setItem('inspectflow_active_dept', 'inspection');
            window.location.href = '/Inspection';
        }
    };

    const handleLogin = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            await auth.signIn({ email, password });
            const currentUser = await auth.me();
            redirectAfterSignIn(currentUser);
        } catch (err) {
            setError(err.message || 'Invalid email or password');
        } finally {
            setLoading(false);
        }
    };

    const handleDevQuickLogin = async (accEmail) => {
        setLoading(true);
        setError('');
        try {
            const user = await auth.devQuickSignIn(accEmail);
            redirectAfterSignIn(user);
        } catch (err) {
            setError(err.message || 'Dev quick sign-in failed');
        } finally {
            setLoading(false);
        }
    };

    const inspectionAccounts = devAccounts.filter((a) => a.group !== 'Expediting & Vendor');
    const expeditingAccounts = devAccounts.filter((a) => a.group === 'Expediting & Vendor');

    return (
        <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
            <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
                <div className="text-center mb-8">
                    <div className="w-16 h-16 bg-gradient-to-br from-indigo-600 to-indigo-700 rounded-lg flex items-center justify-center shadow-lg mx-auto mb-4">
                        <FileText className="w-10 h-10 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold text-gray-900 mb-2">InspectFlow</h1>
                    <p className="text-gray-600">Sign in to your account</p>
                </div>

                <form onSubmit={handleLogin} className="space-y-4">
                    <div>
                        <Label htmlFor="email">Email</Label>
                        <Input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="your@email.com"
                            required
                        />
                    </div>

                    <div>
                        <Label htmlFor="password">Password</Label>
                        <Input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="Enter password"
                            required
                        />
                    </div>

                    {error && (
                        <div className="bg-red-50 text-red-600 p-3 rounded-lg text-sm">
                            {error}
                        </div>
                    )}

                    <Button
                        type="submit"
                        className="w-full"
                        disabled={loading}
                    >
                        {loading ? 'Signing in...' : 'Sign In'}
                    </Button>
                </form>

                <p className="text-sm text-gray-500 mt-6 text-center">
                    Don't have an account?{' '}
                    <a href="/signup" className="text-indigo-600 hover:underline">
                        Sign up
                    </a>
                </p>

                {authMode === 'dev' && devAccounts.length > 0 && (
                    <div className="mt-6 border-t pt-5">
                        <div className="flex items-center justify-center gap-1.5 mb-3">
                            <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                Dev Testing Mode — 1-Click Role Sign-In
                            </p>
                        </div>

                        {inspectionAccounts.length > 0 && (
                            <div className="mb-3">
                                <p className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5 px-1">
                                    Inspection &amp; QA/QC Team
                                </p>
                                <div className="space-y-1.5">
                                    {inspectionAccounts.map((acc) => (
                                        <button
                                            key={acc.email}
                                            type="button"
                                            disabled={loading}
                                            onClick={() => handleDevQuickLogin(acc.email)}
                                            className="w-full flex items-center justify-between px-3 py-2 rounded-lg border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 transition-colors text-left group"
                                        >
                                            <div>
                                                <p className="text-xs font-medium text-gray-800 group-hover:text-indigo-700">{acc.email}</p>
                                                <p className="text-[11px] text-gray-500">{acc.full_name}</p>
                                            </div>
                                            <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${acc.badge}`}>{acc.role_label}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {expeditingAccounts.length > 0 && (
                            <div>
                                <p className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5 px-1">
                                    Expediting &amp; Supplier Team
                                </p>
                                <div className="space-y-1.5">
                                    {expeditingAccounts.map((acc) => (
                                        <button
                                            key={acc.email}
                                            type="button"
                                            disabled={loading}
                                            onClick={() => handleDevQuickLogin(acc.email)}
                                            className="w-full flex items-center justify-between px-3 py-2 rounded-lg border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 transition-colors text-left group"
                                        >
                                            <div>
                                                <p className="text-xs font-medium text-gray-800 group-hover:text-indigo-700">{acc.email}</p>
                                                <p className="text-[11px] text-gray-500">{acc.full_name}</p>
                                            </div>
                                            <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${acc.badge}`}>{acc.role_label}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        <p className="text-[11px] text-gray-400 text-center mt-3">
                            Issues real backend-verified JWT tokens for full RBAC testing (disabled automatically in AUTH_MODE=production)
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}

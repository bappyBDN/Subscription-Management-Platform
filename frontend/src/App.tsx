import { Route, Routes } from 'react-router-dom';

import { RequireAuth, RequireRole } from './auth/AuthProvider';
import { EmptyState } from './components/shared';
import AppLayout from './layouts/AppLayout';
import Approvals from './pages/Approvals';
import AuditLog from './pages/AuditLog';
import Charges from './pages/Charges';
import Dashboard from './pages/Dashboard';
import HandoverSetup from './pages/HandoverSetup';
import HandoverTasks from './pages/HandoverTasks';
import Login from './pages/Login';
import MySubscriptions from './pages/MySubscriptions';
import Reports from './pages/Reports';
import RequestDecision from './pages/RequestDecision';
import RequestDetailPage from './pages/RequestDetail';
import RequestForm from './pages/RequestForm';
import RequestsList from './pages/RequestsList';
import Settings from './pages/Settings';
import SubscriptionDetailPage from './pages/SubscriptionDetail';
import Subscriptions from './pages/Subscriptions';
import Cards from './pages/masters/Cards';
import Employees from './pages/masters/Employees';
import Users from './pages/masters/Users';
import Vendors from './pages/masters/Vendors';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="requests" element={<RequestsList />} />
        <Route path="requests/new" element={<RequestForm />} />
        <Route path="requests/:id" element={<RequestDetailPage />} />
        <Route path="requests/:id/edit" element={<RequestForm />} />
        <Route path="requests/:id/handover" element={<RequireRole roles={['dmd', 'delegate']}><HandoverSetup /></RequireRole>} />
        <Route path="my/subscriptions" element={<MySubscriptions />} />
        <Route path="my/handover-tasks" element={<HandoverTasks />} />
        <Route path="approvals" element={<RequireRole roles={['manager', 'dmd']}><Approvals /></RequireRole>} />
        <Route path="approvals/:id" element={<RequireRole roles={['manager', 'dmd']}><RequestDecision /></RequireRole>} />
        <Route path="subscriptions" element={<RequireRole roles={['dmd', 'delegate']}><Subscriptions /></RequireRole>} />
        <Route path="subscriptions/:id" element={<RequireRole roles={['dmd', 'delegate']}><SubscriptionDetailPage /></RequireRole>} />
        <Route path="charges" element={<RequireRole roles={['dmd', 'delegate']}><Charges /></RequireRole>} />
        <Route path="reports" element={<RequireRole roles={['manager', 'dmd', 'delegate']}><Reports /></RequireRole>} />
        <Route path="masters/employees" element={<RequireRole roles={['dmd', 'delegate']}><Employees /></RequireRole>} />
        <Route path="masters/vendors" element={<RequireRole roles={['dmd', 'delegate']}><Vendors /></RequireRole>} />
        <Route path="masters/cards" element={<RequireRole roles={['dmd', 'delegate']}><Cards /></RequireRole>} />
        <Route path="masters/users" element={<RequireRole roles={['dmd', 'delegate']}><Users /></RequireRole>} />
        <Route path="settings" element={<RequireRole roles={['dmd']}><Settings /></RequireRole>} />
        <Route path="audit" element={<RequireRole roles={['dmd', 'delegate']}><AuditLog /></RequireRole>} />
        <Route path="*" element={<EmptyState title="Page not found" hint="Use the menu to find what you need." />} />
      </Route>
    </Routes>
  );
}

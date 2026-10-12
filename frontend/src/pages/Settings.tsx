import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';

import { settingsApi } from '@/api/masters';
import { ErrorState, LoadingRows } from '@/components/shared';
import { Button, Card, Checkbox, Field, Input, PageHeader, Select } from '@/components/ui';
import { useAction } from '@/hooks';

interface SettingsForm {
  week_start: string;
  year_start_month: string;
  monthly_budget_bdt: string;
  default_fx_rate_usd: string;
  approval_sla_days: string;
  allow_urgent_override: boolean;
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const isTrue = (v: string | undefined) => ['1', 'true', 'yes', 'on'].includes(String(v).toLowerCase());

export default function Settings() {
  const query = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get });
  const { register, handleSubmit, reset, formState } = useForm<SettingsForm>();

  useEffect(() => {
    const s = query.data;
    if (!s) return;
    reset({
      week_start: s.week_start,
      year_start_month: s.year_start_month,
      monthly_budget_bdt: s.monthly_budget_bdt,
      default_fx_rate_usd: s.default_fx_rate_usd,
      approval_sla_days: s.approval_sla_days,
      allow_urgent_override: isTrue(s.allow_urgent_override),
    });
  }, [query.data, reset]);

  const save = useAction(
    (v: SettingsForm) =>
      settingsApi.save({
        week_start: v.week_start,
        year_start_month: Number(v.year_start_month),
        monthly_budget_bdt: v.monthly_budget_bdt || '0',
        default_fx_rate_usd: v.default_fx_rate_usd,
        approval_sla_days: Number(v.approval_sla_days),
        allow_urgent_override: v.allow_urgent_override,
      }),
    { success: 'Settings saved' },
  );

  if (query.isLoading) return <LoadingRows rows={6} />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  const e = formState.errors;

  return (
    <form onSubmit={handleSubmit((v) => save.mutate(v))} noValidate>
      <PageHeader title="Settings" subtitle="These change how cost is totalled and how approvals behave for everyone." />
      <div className="grid max-w-3xl grid-cols-1 gap-4">
        <Card title="Cost periods">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Week starts on">
              <Select {...register('week_start')}>
                <option value="sat">Saturday</option>
                <option value="sun">Sunday</option>
                <option value="mon">Monday</option>
              </Select>
            </Field>
            <Field label="Year starts in" hint="Use July for the fiscal year.">
              <Select {...register('year_start_month')}>
                {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </Select>
            </Field>
          </div>
        </Card>
        <Card title="Budget and currency">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Monthly budget (BDT)" hint="0 = no budget. Admins are notified at 80% and 100%." error={e.monthly_budget_bdt?.message}>
              <Input type="number" step="0.01" min={0} {...register('monthly_budget_bdt', { validate: (v) => v === '' || Number(v) >= 0 || 'Cannot be negative' })} />
            </Field>
            <Field label="Default FX rate (BDT per USD)" required error={e.default_fx_rate_usd?.message}>
              <Input type="number" step="0.01" min={0} {...register('default_fx_rate_usd', { required: 'Enter the rate', validate: (v) => Number(v) > 0 || 'Must be more than 0' })} />
            </Field>
          </div>
        </Card>
        <Card title="Approvals">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Approval SLA (days)" hint="Requests waiting longer are shown in red." error={e.approval_sla_days?.message}>
              <Input type="number" min={1} max={30} {...register('approval_sla_days', { required: 'Enter the number of days', validate: (v) => (Number(v) >= 1 && Number(v) <= 30) || 'Between 1 and 30 days' })} />
            </Field>
            <div className="flex items-end pb-2">
              <Checkbox label="Allow urgent override (DMD Sir may skip the manager step)" {...register('allow_urgent_override')} />
            </div>
          </div>
        </Card>
        <div>
          <Button type="submit" loading={save.isPending} disabled={!formState.isDirty}>Save settings</Button>
        </div>
      </div>
    </form>
  );
}

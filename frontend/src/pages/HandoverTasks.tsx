import { useQuery } from '@tanstack/react-query';

import { handoverApi } from '@/api/requests';
import { EmptyState, QueryState } from '@/components/shared';
import { Badge, Button, Card, PageHeader } from '@/components/ui';
import { useAction } from '@/hooks';
import { fmtDate, fmtDateTime, todayIso } from '@/lib/format';

export default function HandoverTasks() {
  const query = useQuery({ queryKey: ['handover-tasks'], queryFn: handoverApi.tasks });
  const done = useAction((id: number) => handoverApi.handedOver(id), { success: 'Marked as handed over — the requester will confirm' });
  const today = todayIso();

  return (
    <>
      <PageHeader title="Handover tasks" subtitle="Colleagues you have been asked to hand access over to." />
      <Card>
        <QueryState
          query={query}
          isEmpty={(d) => d.length === 0}
          empty={<EmptyState title="No handover tasks" hint="When DMD Sir's office asks you to hand over a login, it appears here." />}
        >
          {(tasks) => (
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {tasks.map((t) => {
                const overdue = !!t.due_date && t.due_date < today && !t.handed_over_at;
                return (
                  <li key={t.handover_id} className="rounded-lg border border-slate-200 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900">{t.tool_name} <span className="font-normal text-slate-500">{t.plan_name}</span></p>
                        <p className="text-sm text-slate-600">Hand over to {t.requester_name} ({t.requester_code})</p>
                        <p className="text-xs text-slate-500">{t.req_no}</p>
                      </div>
                      {t.handed_over_at ? <Badge tone="green">Handed over</Badge> : overdue ? <Badge tone="red">Overdue</Badge> : <Badge tone="amber">To do</Badge>}
                    </div>
                    {t.note && <p className="mt-2 whitespace-pre-wrap rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">{t.note}</p>}
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs text-slate-500">
                        {t.handed_over_at ? `Handed over ${fmtDateTime(t.handed_over_at)} — waiting for the requester to confirm` : `Due ${fmtDate(t.due_date)}`}
                      </span>
                      {!t.handed_over_at && (
                        <Button size="sm" loading={done.isPending && done.variables === t.handover_id} onClick={() => done.mutate(t.handover_id)}>
                          Mark handed over
                        </Button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </QueryState>
      </Card>
    </>
  );
}

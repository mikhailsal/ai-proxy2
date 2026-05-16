import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RequestDetail } from '../../src/components/RequestDetail/RequestDetail';
import { makeRequestDetail, makeRequestSummary, renderWithApi } from './detail-and-chat.helpers';

describe('RequestDetail cost rendering', () => {
  it('adds upstream inference cost only for BYOK detail payloads', async () => {
    const detail = makeRequestDetail({
      cost: 0.000069125,
      response_body: {
        usage: {
          cost: 0.000069125,
          is_byok: true,
          cost_details: {
            upstream_inference_cost: 0.0013825,
          },
        },
        choices: [{ message: { role: 'assistant', content: 'priced' } }],
      },
    });
    const api = {
      downloadExport: vi.fn().mockResolvedValue(undefined),
      getRequest: vi.fn().mockResolvedValue(detail),
    };

    renderWithApi(
      <RequestDetail onClose={vi.fn()} requestId="req-cost" requestSummary={makeRequestSummary({ cost: 0.000069125 })} />,
      api,
    );

    await waitFor(() => expect(screen.getByText('$0.001452')).toBeInTheDocument());
  });

  it('does not double count upstream inference cost for non-BYOK detail payloads', async () => {
    const detail = makeRequestDetail({
      cost: 0.0003039,
      response_body: {
        usage: {
          cost: 0.0003039,
          is_byok: false,
          cost_details: {
            upstream_inference_cost: 0.0003039,
          },
        },
        choices: [{ message: { role: 'assistant', content: 'priced' } }],
      },
    });
    const api = {
      downloadExport: vi.fn().mockResolvedValue(undefined),
      getRequest: vi.fn().mockResolvedValue(detail),
    };

    renderWithApi(
      <RequestDetail onClose={vi.fn()} requestId="req-cost-non-byok" requestSummary={makeRequestSummary({ cost: 0.0003039 })} />,
      api,
    );

    await waitFor(() => expect(screen.getByText('$0.000304')).toBeInTheDocument());
  });
});
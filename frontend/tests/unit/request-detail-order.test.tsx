import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { RequestDetail } from '../../src/components/RequestDetail/RequestDetail';
import { makeRequestDetail, makeRequestSummary, renderWithApi } from './detail-and-chat.helpers';

afterEach(() => {
  vi.restoreAllMocks();
});

it('renders request-body keys in API order in plain view', { timeout: 15000 }, async () => {
  const api = {
    downloadExport: vi.fn().mockResolvedValue(undefined),
    getRequest: vi.fn().mockResolvedValue(
      makeRequestDetail({
        request_body: {
          omega_top: 'ORDER_PROBE_20260510_A',
          model: 'openai/gpt-4o',
          tools: [
            {
              type: 'function',
              function: {
                name: 'tool_second',
                parameters: {
                  type: 'object',
                  properties: { zeta_nested: { type: 'string' }, alpha_nested: { type: 'string' } },
                  required: ['zeta_required', 'alpha_required'],
                },
              },
            },
            {
              type: 'function',
              function: {
                name: 'tool_first',
                parameters: {
                  type: 'object',
                  properties: { gamma_nested: { type: 'string' }, beta_nested: { type: 'string' } },
                  required: ['gamma_required', 'beta_required'],
                },
              },
            },
          ],
          messages: [{ role: 'user', content: 'ORDER_PROBE_20260510_A' }],
        },
        client_request_body: null,
      }),
    ),
  };

  const { container } = renderWithApi(
    <RequestDetail onClose={vi.fn()} requestId="req-order" requestSummary={makeRequestSummary({})} />,
    api,
  );

  await waitFor(() => expect(screen.getByText('Request Body')).toBeInTheDocument());

  for (const button of screen.getAllByTitle('expand')) {
    await userEvent.click(button);
  }

  const text = container.textContent ?? '';
  expect(text.indexOf('"omega_top"')).toBeLessThan(text.indexOf('"model"'));
  expect(text.indexOf('"model"')).toBeLessThan(text.indexOf('"tools"'));
  expect(text.indexOf('"tools"')).toBeLessThan(text.indexOf('"messages"'));
  expect(text.indexOf('tool_second')).toBeLessThan(text.indexOf('tool_first'));
});
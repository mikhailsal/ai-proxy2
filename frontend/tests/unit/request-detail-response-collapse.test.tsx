import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DiffJsonViewer } from '../../src/components/JsonViewer/DiffJsonViewer';
import { JsonViewer } from '../../src/components/JsonViewer/JsonViewer';
import { RequestDetail } from '../../src/components/RequestDetail/RequestDetail';
import { makeRequestDetail, makeRequestSummary, renderWithApi } from './detail-and-chat.helpers';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Response collapse defaults', () => {
  it('keeps top-level primitive paths visible while collapsing nested ones', async () => {
    render(
      <JsonViewer
        data={{ id: 'abc123', meta: { nestedId: 'hidden' }, choices: [{ message: { content: 'reply' } }] }}
        collapsedPaths={['id', 'meta.nestedId']}
        expandedPaths={['choices']}
      />,
    );

    expect(screen.getByText('"id"')).toBeInTheDocument();
    expect(screen.getByText('"abc123"')).toBeInTheDocument();
    expect(screen.getByText('"nestedId"')).toBeInTheDocument();
    expect(screen.queryByText('"hidden"')).not.toBeInTheDocument();
    expect(screen.getByText('"reply"')).toBeInTheDocument();

    await userEvent.click(screen.getAllByTitle('expand')[0]);

    expect(screen.getByText('"hidden"')).toBeInTheDocument();
  });

  it('collapses non-choice response fields in diff view while keeping choices expanded', async () => {
    const detail = makeRequestDetail({
      response_body: {
        id: 'provider-id',
        model: 'provider-model',
        usage: { prompt_tokens: 42 },
        object: 'chat.completion',
        choices: [{ index: 0, message: { role: 'assistant', content: 'deep reply' } }],
      },
      client_response_body: {
        id: 'provider-id',
        model: 'provider-model',
        usage: { prompt_tokens: 42 },
        object: 'chat.completion',
        choices: [{ index: 0, message: { role: 'assistant', content: 'deep reply' } }],
        ai_proxy_route: 'provider:mapped-model',
      },
    });
    const api = {
      downloadExport: vi.fn().mockResolvedValue(undefined),
      getRequest: vi.fn().mockResolvedValue(detail),
    };

    renderWithApi(
      <RequestDetail onClose={vi.fn()} requestId="req-response-collapse" requestSummary={makeRequestSummary({})} />,
      api,
    );

    await waitFor(() => expect(screen.getByText('Response Body (Provider → Client)')).toBeInTheDocument());

    expect(screen.getByText('"id"')).toBeInTheDocument();
    expect(screen.getByText('"model"')).toBeInTheDocument();
    expect(screen.getByText('"provider-id"')).toBeInTheDocument();
    expect(screen.getByText('"provider-model"')).toBeInTheDocument();
    expect(screen.getByText('"chat.completion"')).toBeInTheDocument();
    expect(screen.queryByText('"prompt_tokens"')).not.toBeInTheDocument();
    expect(screen.getByText('"choices"')).toBeInTheDocument();
    expect(screen.getByText('"assistant"')).toBeInTheDocument();
    expect(screen.getByText('"deep reply"')).toBeInTheDocument();
  });

  it('collapses nested scalar variants and preserves highlight labels on expand', async () => {
    render(
      <JsonViewer
        data={{
          meta: {
            nil: null,
            flag: true,
            count: 7,
            text: 'hidden',
          },
        }}
        collapsedPaths={['meta.nil', 'meta.flag', 'meta.count', 'meta.text']}
        highlightRules={[{ path: 'meta.text', label: 'tagged', background: 'rgba(187, 128, 9, 0.15)' }]}
      />,
    );

    expect(screen.queryByText('"hidden"')).not.toBeInTheDocument();
    expect(screen.queryByText('true')).not.toBeInTheDocument();
    expect(screen.queryByText('7')).not.toBeInTheDocument();
    expect(screen.getAllByTitle('expand')).toHaveLength(4);

    for (const button of screen.getAllByTitle('expand')) {
      await userEvent.click(button);
    }

    expect(screen.getByText('null')).toBeInTheDocument();
    expect(screen.getByText('true')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('"hidden"')).toBeInTheDocument();
    expect(screen.getByText('tagged')).toBeInTheDocument();
  });

  it('handles non-json fallback values and collapsed nested diffs', async () => {
    render(
      <div>
        <JsonViewer data={Symbol.for('json-fallback') as unknown} />
        <pre>
          <DiffJsonViewer
            left={{ meta: { status: 'before', items: [1, 2] } }}
            right={{ meta: { status: 'after', items: [1, 2] } }}
            collapsedPaths={['meta.status', 'meta.items']}
          />
        </pre>
        <pre><DiffJsonViewer left={null} right={Symbol.for('diff-fallback') as unknown} /></pre>
      </div>,
    );

    expect(screen.getByText('Symbol(json-fallback)')).toBeInTheDocument();
    expect(screen.getByText('Symbol(diff-fallback)')).toBeInTheDocument();
    expect(screen.getByText('[ 2 items ]')).toBeInTheDocument();
    expect(screen.queryByText('before')).not.toBeInTheDocument();
    expect(screen.queryByText('after')).not.toBeInTheDocument();

    const expandButtons = screen.getAllByTitle('expand');
    await userEvent.click(expandButtons[0]);

    expect(screen.getByText('"before"')).toBeInTheDocument();
    expect(screen.getByText('"after"')).toBeInTheDocument();
    expect(screen.getByText('→')).toBeInTheDocument();
  });
});
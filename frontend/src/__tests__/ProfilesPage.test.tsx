import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./testUtils";
import ProfilesPage from "@/pages/ProfilesPage";
import type { TradingProfile } from "@/api/profiles";

vi.mock("@/hooks/useProfiles", () => ({
  useProfiles: vi.fn(),
  useCreateProfile: vi.fn(),
  useUpdateProfile: vi.fn(),
  useDeleteProfile: vi.fn(),
}));

import {
  useProfiles,
  useCreateProfile,
  useUpdateProfile,
  useDeleteProfile,
} from "@/hooks/useProfiles";

const mockUseProfiles = vi.mocked(useProfiles);
const mockUseCreateProfile = vi.mocked(useCreateProfile);
const mockUseUpdateProfile = vi.mocked(useUpdateProfile);
const mockUseDeleteProfile = vi.mocked(useDeleteProfile);

const PROFILE_A: TradingProfile = {
  id: 1,
  name: "Swing Trader",
  style: "Hold 2-5 days",
  default_includes: ["quotes", "ohlc"],
  default_provider: "claude",
  default_model: "claude-sonnet-4-6",
  active: true,
};

function makeCreate(impl?: (body: unknown, opts?: { onSuccess?: () => void }) => void) {
  const mockMutate = vi.fn();
  mockMutate.mockImplementation(impl ?? ((_body, opts) => opts?.onSuccess?.()));
  mockUseCreateProfile.mockReturnValue({ mutate: mockMutate, isPending: false } as never);
  return mockMutate;
}

function makeUpdate(impl?: (args: unknown, opts?: { onSuccess?: () => void }) => void) {
  const mockMutate = vi.fn();
  mockMutate.mockImplementation(impl ?? ((_args, opts) => opts?.onSuccess?.()));
  mockUseUpdateProfile.mockReturnValue({ mutate: mockMutate, isPending: false } as never);
  return mockMutate;
}

function makeDelete() {
  const mockMutate = vi.fn();
  mockUseDeleteProfile.mockReturnValue({ mutate: mockMutate, isPending: false } as never);
  return mockMutate;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseProfiles.mockReturnValue({ data: [] } as never);
  makeCreate();
  makeUpdate();
  makeDelete();
});

describe("ProfilesPage", () => {
  it("renders form blank by default with default_includes prefilled", () => {
    renderWithProviders(<ProfilesPage />);
    expect(screen.getByPlaceholderText("Profile name")).toHaveValue("");
    // quotes, positions, breadth should be checked
    const quotesCheckbox = screen.getByRole("checkbox", { name: /quotes/i });
    const positionsCheckbox = screen.getByRole("checkbox", { name: /positions/i });
    const breadthCheckbox = screen.getByRole("checkbox", { name: /breadth/i });
    expect(quotesCheckbox).toBeChecked();
    expect(positionsCheckbox).toBeChecked();
    expect(breadthCheckbox).toBeChecked();
    // ohlc should NOT be checked
    const ohlcCheckbox = screen.getByRole("checkbox", { name: /ohlc/i });
    expect(ohlcCheckbox).not.toBeChecked();
  });

  it("typing into name input updates the field", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);
    const nameInput = screen.getByPlaceholderText("Profile name");
    await user.type(nameInput, "My Profile");
    expect(nameInput).toHaveValue("My Profile");
  });

  it("submitting form with valid name calls create.mutate with the right body", async () => {
    const user = userEvent.setup();
    const createMutate = vi.fn();
    mockUseCreateProfile.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    renderWithProviders(<ProfilesPage />);
    await user.type(screen.getByPlaceholderText("Profile name"), "Scalper");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    expect(createMutate).toHaveBeenCalledOnce();
    const [body] = createMutate.mock.calls[0];
    expect(body).toMatchObject({
      name: "Scalper",
      default_includes: expect.arrayContaining(["quotes", "positions", "breadth"]),
    });
  });

  it("after create succeeds, form resets to BLANK_DRAFT", async () => {
    const user = userEvent.setup();
    // createMutate immediately invokes onSuccess
    const createMutate = vi.fn().mockImplementation((_body, opts) => opts?.onSuccess?.());
    mockUseCreateProfile.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    renderWithProviders(<ProfilesPage />);
    const nameInput = screen.getByPlaceholderText("Profile name");
    await user.type(nameInput, "Temp Name");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(nameInput).toHaveValue(""));
  });

  it("toggling an unchecked section checkbox adds it to default_includes", async () => {
    const user = userEvent.setup();
    const createMutate = vi.fn();
    mockUseCreateProfile.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    renderWithProviders(<ProfilesPage />);
    const ohlcCheckbox = screen.getByRole("checkbox", { name: /ohlc/i });
    expect(ohlcCheckbox).not.toBeChecked();
    await user.click(ohlcCheckbox);
    expect(ohlcCheckbox).toBeChecked();

    // Submit and verify ohlc is in body
    await user.type(screen.getByPlaceholderText("Profile name"), "X");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    const [body] = createMutate.mock.calls[0];
    expect(body.default_includes).toContain("ohlc");
  });

  it("toggling a checked section checkbox removes it from default_includes", async () => {
    const user = userEvent.setup();
    const createMutate = vi.fn();
    mockUseCreateProfile.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    renderWithProviders(<ProfilesPage />);
    const quotesCheckbox = screen.getByRole("checkbox", { name: /quotes/i });
    expect(quotesCheckbox).toBeChecked();
    await user.click(quotesCheckbox);
    expect(quotesCheckbox).not.toBeChecked();

    await user.type(screen.getByPlaceholderText("Profile name"), "X");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    const [body] = createMutate.mock.calls[0];
    expect(body.default_includes).not.toContain("quotes");
  });

  it("clicking Edit on a profile populates the form", async () => {
    mockUseProfiles.mockReturnValue({ data: [PROFILE_A] } as never);
    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);

    const editButton = screen.getByRole("button", { name: /edit/i });
    await user.click(editButton);

    expect(screen.getByPlaceholderText("Profile name")).toHaveValue("Swing Trader");
    expect(screen.getByRole("button", { name: /save/i })).toBeInTheDocument();
  });

  it("submitting while editing calls update.mutate not create", async () => {
    mockUseProfiles.mockReturnValue({ data: [PROFILE_A] } as never);
    const createMutate = vi.fn();
    const updateMutate = vi.fn();
    mockUseCreateProfile.mockReturnValue({ mutate: createMutate, isPending: false } as never);
    mockUseUpdateProfile.mockReturnValue({ mutate: updateMutate, isPending: false } as never);

    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);

    await user.click(screen.getByRole("button", { name: /edit/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(updateMutate).toHaveBeenCalledOnce();
    expect(createMutate).not.toHaveBeenCalled();
    const [args] = updateMutate.mock.calls[0];
    expect(args.id).toBe(PROFILE_A.id);
  });

  it("after update succeeds, editing clears and draft resets", async () => {
    mockUseProfiles.mockReturnValue({ data: [PROFILE_A] } as never);
    const updateMutate = vi.fn().mockImplementation((_args, opts) => opts?.onSuccess?.());
    mockUseUpdateProfile.mockReturnValue({ mutate: updateMutate, isPending: false } as never);

    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);

    await user.click(screen.getByRole("button", { name: /edit/i }));
    expect(screen.getByPlaceholderText("Profile name")).toHaveValue("Swing Trader");

    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Profile name")).toHaveValue("");
      expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    });
  });

  it("clicking Delete calls del.mutate with profile id", async () => {
    mockUseProfiles.mockReturnValue({ data: [PROFILE_A] } as never);
    const delMutate = vi.fn();
    mockUseDeleteProfile.mockReturnValue({ mutate: delMutate, isPending: false } as never);

    const user = userEvent.setup();
    renderWithProviders(<ProfilesPage />);

    await user.click(screen.getByRole("button", { name: /delete/i }));
    expect(delMutate).toHaveBeenCalledWith(PROFILE_A.id);
  });

  it("renders existing profiles in a list", () => {
    mockUseProfiles.mockReturnValue({ data: [PROFILE_A] } as never);
    renderWithProviders(<ProfilesPage />);
    expect(screen.getByTestId("profile-row-Swing Trader")).toBeInTheDocument();
    expect(screen.getByText("Swing Trader")).toBeInTheDocument();
  });
});

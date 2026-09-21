import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { FileUploadForm } from "./FileUploadForm";

const meta = {
  title: "Thread/FileUploadForm",
  component: FileUploadForm,
  tags: ["ai-generated"],
  parameters: {
    docs: {
      description: {
        component:
          "Upload a document to the Files API. The file input, kind and ticker sit " +
          "in one fieldset; the help text under the file input states the 32 MB " +
          "ceiling the server enforces (a larger file comes back as a 413 " +
          "`file_too_large`, which the form reports verbatim rather than as a " +
          "generic failure).",
      },
    },
  },
} satisfies Meta<typeof FileUploadForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvas }) => {
    await expect(canvas.getByLabelText("File")).toBeVisible();
    await expect(canvas.getByLabelText("Kind")).toBeVisible();
    await expect(canvas.getByRole("button", { name: "Upload" })).toBeVisible();
  },
};

/** Submitting with no file chosen reports it inline instead of POSTing. */
export const MissingFile: Story = {
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Upload" }));
    await expect(canvas.getByRole("alert")).toHaveTextContent("Choose a file to upload.");
  },
};

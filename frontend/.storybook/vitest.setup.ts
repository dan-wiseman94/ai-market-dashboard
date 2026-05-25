import * as a11yAddonAnnotations from "@storybook/addon-a11y/preview";
import { setProjectAnnotations } from "@storybook/react-vite";
import { beforeAll } from "vitest";
import * as projectAnnotations from "./preview";

// Apply the same decorators/parameters the running Storybook uses (dark canvas
// + globals.css) so the vitest browser lane renders stories identically.
const project = setProjectAnnotations([a11yAddonAnnotations, projectAnnotations]);

beforeAll(project.beforeAll);

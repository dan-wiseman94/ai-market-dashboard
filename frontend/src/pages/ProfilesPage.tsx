import { useProfiles } from "@/hooks/useProfiles";
import { useAgentPresets } from "@/hooks/useAgentPresets";
import { ProfileForm } from "./profiles/ProfileForm";
import { ProfileList } from "./profiles/ProfileList";
import { PresetForm } from "./profiles/PresetForm";
import { PresetList } from "./profiles/PresetList";
import { useProfileForm } from "./profiles/useProfileForm";
import { usePresetForm } from "./profiles/usePresetForm";

export default function ProfilesPage() {
  const { data: profiles } = useProfiles();
  const { data: presets } = useAgentPresets();
  const profileForm = useProfileForm();
  const presetForm = usePresetForm();

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold">Trading profiles</h1>

      <ProfileForm form={profileForm} />
      <ProfileList profiles={profiles ?? []} onEdit={profileForm.startEdit} />

      <div className="flex items-center justify-between pt-2">
        <h2 className="text-xl font-semibold">Agent presets</h2>
        {!presetForm.showForm && !presetForm.editing && (
          <button
            type="button"
            onClick={() => presetForm.setShowForm(true)}
            className="px-3 py-1.5 text-sm rounded bg-slate-800 hover:bg-slate-700"
          >New preset</button>
        )}
      </div>

      {(presetForm.showForm || presetForm.editing) && <PresetForm form={presetForm} />}

      <PresetList presets={presets ?? []} onEdit={presetForm.startEdit} />
    </main>
  );
}

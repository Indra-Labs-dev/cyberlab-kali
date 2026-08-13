// Minimal Project shape used where only the name needs to be displayed
// (e.g. resolving an Asset's project_id to a label, a <select> of
// projects). backend/app/schemas/project.py::ProjectResponse carries more
// fields (description/status/timestamps) -- not included here since no
// current consumer of this minimal type reads them; pages/projects/
// index.vue's richer ProjectSummary (with target/job/finding/lab counts)
// is a different, single-purpose shape and stays local for now.
export interface Project {
  id: string;
  name: string;
}

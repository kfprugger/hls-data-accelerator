using CommandLine;

namespace ExtensionSupport
{
    public class CommandLineOptions
    {
        [Option('i', "inputfile",  Required =true, SetName = "file", HelpText = "Input file to be processed. (Note: you required to use input file or input folder option)")]
        public string InputFile { get; set; }

        [Option('o', "outputfile",  SetName = "file", HelpText = "Output file to be generated.")]
        public string OutputFile { get; set; }

        [Option('f', "inputfolder", Required =true, SetName = "folder", HelpText = "Input folder to be processed. (Note: you required to use input file or input folder option)")]
        public string InputFolder { get; set; }

        [Option('g', "outputfolder", SetName = "folder", HelpText = "Output folder to be generated.")]
        public string OutputFolder { get; set; }

    } 
}